"""设置页面 - API配置（Fluent风格）"""

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSpacerItem, QSizePolicy

from qfluentwidgets import (
    ScrollArea, StrongBodyLabel, CaptionLabel,
    LineEdit, PasswordLineEdit, PrimaryPushButton, PushButton,
    InfoBar, InfoBarPosition, CardWidget, TitleLabel, FluentIcon as FIF,
    TransparentToolButton, SubtitleLabel
)

from src.utils.config import settings, get_app_dir
from src.services.llm_service import llm_service


class ApiKeyItem(QWidget):
    """单个 API Key 配置项"""

    def __init__(self, key_value="", index=0, parent=None):
        super().__init__(parent)
        self.index = index
        self._init_ui(key_value)

    def _init_ui(self, key_value):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(8)

        # Key 编号
        self.index_label = CaptionLabel(f"Key {self.index + 1}")
        self.index_label.setFixedWidth(50)
        layout.addWidget(self.index_label)

        # Key 输入框
        self.key_edit = PasswordLineEdit()
        # 确保 key_value 是字符串
        key_str = str(key_value) if key_value else ""
        self.key_edit.setText(key_str)
        self.key_edit.setPlaceholderText(f"输入 API Key {self.index + 1}...")
        self.key_edit.setClearButtonEnabled(True)
        layout.addWidget(self.key_edit, 1)

        # 测试按钮
        self.test_btn = PushButton("测试")
        self.test_btn.setFixedWidth(60)
        layout.addWidget(self.test_btn)

        # 状态标签
        self.status_label = CaptionLabel("")
        self.status_label.setFixedWidth(80)
        layout.addWidget(self.status_label)

        # 删除按钮
        self.delete_btn = TransparentToolButton(FIF.DELETE)
        self.delete_btn.setFixedSize(28, 28)
        layout.addWidget(self.delete_btn)

    def get_key(self):
        return self.key_edit.text().strip()

    def set_index(self, index):
        self.index = index
        self.index_label.setText(f"Key {index + 1}")
        self.key_edit.setPlaceholderText(f"输入 API Key {index + 1}...")

    def set_testing(self, testing):
        self.test_btn.setEnabled(not testing)
        self.test_btn.setText("..." if testing else "测试")

    def set_status(self, success, message):
        if success:
            self.status_label.setStyleSheet("color: green;")
            self.status_label.setText("✓ 可用")
        else:
            self.status_label.setStyleSheet("color: red;")
            self.status_label.setText("✗ 失败")


class SettingsPage(ScrollArea):
    """设置页面 - Fluent风格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._api_key_items = []  # 存储 ApiKeyItem 列表
        self._test_workers = []   # 存储测试 worker

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        # 主容器
        self.view = QWidget()
        self.setWidget(self.view)

        layout = QVBoxLayout(self.view)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(24)

        # 标题
        title = TitleLabel("系统设置")
        layout.addWidget(title)

        # 说明
        desc = CaptionLabel("配置 AI 模型的 API 密钥和服务地址")
        layout.addWidget(desc)

        # 规则解析模型配置卡片
        rules_card = CardWidget()
        rules_card.setBorderRadius(12)
        rules_layout = QVBoxLayout(rules_card)
        rules_layout.setContentsMargins(24, 20, 24, 24)
        rules_layout.setSpacing(16)

        rules_title = StrongBodyLabel("规则解析模型 (DeepSeek)")
        rules_desc = CaptionLabel("用于解析品牌规范文档，仅需文本处理能力")
        rules_layout.addWidget(rules_title)
        rules_layout.addWidget(rules_desc)

        # API Key
        key_layout = QHBoxLayout()
        key_label = StrongBodyLabel("API Key")
        self.deepseek_key_edit = PasswordLineEdit()
        self.deepseek_key_edit.setPlaceholderText("输入 DeepSeek API 密钥...")
        self.deepseek_key_edit.setClearButtonEnabled(True)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.deepseek_key_edit, 1)
        rules_layout.addLayout(key_layout)

        # API Base
        base_layout = QHBoxLayout()
        base_label = StrongBodyLabel("API 地址")
        self.deepseek_base_edit = LineEdit()
        self.deepseek_base_edit.setPlaceholderText("https://api.deepseek.com")
        self.deepseek_base_edit.setClearButtonEnabled(True)
        base_layout.addWidget(base_label)
        base_layout.addWidget(self.deepseek_base_edit, 1)
        rules_layout.addLayout(base_layout)

        # Model
        model_layout = QHBoxLayout()
        model_label = StrongBodyLabel("模型名称")
        self.deepseek_model_edit = LineEdit()
        self.deepseek_model_edit.setPlaceholderText("deepseek-chat")
        self.deepseek_model_edit.setClearButtonEnabled(True)
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.deepseek_model_edit, 1)
        rules_layout.addLayout(model_layout)

        # 测试按钮行
        test_layout = QHBoxLayout()
        self.deepseek_test_btn = PushButton("测试连接")
        self.deepseek_test_btn.setIcon(FIF.PLAY)
        self.deepseek_test_btn.clicked.connect(self._test_deepseek)
        test_layout.addWidget(self.deepseek_test_btn)

        self.deepseek_status = CaptionLabel("")
        test_layout.addWidget(self.deepseek_status)
        test_layout.addStretch()
        rules_layout.addLayout(test_layout)

        layout.addWidget(rules_card)

        # 海报分析模型配置卡片 - 支持多 Key
        audit_card = CardWidget()
        audit_card.setBorderRadius(12)
        audit_layout = QVBoxLayout(audit_card)
        audit_layout.setContentsMargins(24, 20, 24, 24)
        audit_layout.setSpacing(16)

        # 标题行
        title_row = QHBoxLayout()
        audit_title = StrongBodyLabel("海报分析模型 (Doubao/豆包)")
        title_row.addWidget(audit_title)
        title_row.addStretch()
        audit_layout.addLayout(title_row)

        audit_desc = CaptionLabel("用于审核设计图片，需要多模态视觉能力。支持配置多个 API Key 并发调用，避免限流。")
        audit_layout.addWidget(audit_desc)

        # API Keys 区域
        keys_title = QHBoxLayout()
        keys_label = StrongBodyLabel("API Keys")
        self.add_key_btn = PushButton("添加 Key")
        self.add_key_btn.setIcon(FIF.ADD)
        self.add_key_btn.setFixedHeight(28)
        self.add_key_btn.clicked.connect(self._add_api_key)
        keys_title.addWidget(keys_label)
        keys_title.addStretch()
        keys_title.addWidget(self.add_key_btn)
        audit_layout.addLayout(keys_title)

        # Keys 列表容器
        self.keys_container = QWidget()
        self.keys_layout = QVBoxLayout(self.keys_container)
        self.keys_layout.setContentsMargins(0, 0, 0, 0)
        self.keys_layout.setSpacing(4)
        audit_layout.addWidget(self.keys_container)

        # API Base
        base_layout2 = QHBoxLayout()
        base_label2 = StrongBodyLabel("API 地址")
        self.doubao_base_edit = LineEdit()
        self.doubao_base_edit.setPlaceholderText("https://ark.cn-beijing.volces.com/api/v3")
        self.doubao_base_edit.setClearButtonEnabled(True)
        base_layout2.addWidget(base_label2)
        base_layout2.addWidget(self.doubao_base_edit, 1)
        audit_layout.addLayout(base_layout2)

        # Model
        model_layout2 = QHBoxLayout()
        model_label2 = StrongBodyLabel("模型名称")
        self.doubao_model_edit = LineEdit()
        self.doubao_model_edit.setPlaceholderText("doubao-vision-pro-32k")
        self.doubao_model_edit.setClearButtonEnabled(True)
        model_layout2.addWidget(model_label2)
        model_layout2.addWidget(self.doubao_model_edit, 1)
        audit_layout.addLayout(model_layout2)

        # 批量测试按钮行
        test_layout2 = QHBoxLayout()
        self.test_all_btn = PushButton("测试全部")
        self.test_all_btn.setIcon(FIF.PLAY)
        self.test_all_btn.clicked.connect(self._test_all_doubao_keys)
        test_layout2.addWidget(self.test_all_btn)

        self.doubao_status = CaptionLabel("")
        test_layout2.addWidget(self.doubao_status)
        test_layout2.addStretch()
        audit_layout.addLayout(test_layout2)

        layout.addWidget(audit_card)

        # 保存按钮
        btn_layout = QHBoxLayout()
        save_btn = PrimaryPushButton("保存配置")
        save_btn.clicked.connect(self._save_api_config)
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

    def _load_settings(self):
        """加载设置"""
        self.deepseek_key_edit.setText(settings.deepseek_api_key or "")
        self.deepseek_base_edit.setText(settings.deepseek_api_base or "")
        self.deepseek_model_edit.setText(settings.deepseek_model or "")

        self.doubao_base_edit.setText(settings.openai_api_base or "")
        self.doubao_model_edit.setText(settings.doubao_model or "")

        # 加载多个 API Keys
        keys = settings.get_openai_api_keys()
        if keys:
            for key in keys:
                if key and isinstance(key, str):
                    self._add_api_key(key)

        # 如果没有 Key，添加一个空项
        if not self._api_key_items:
            self._add_api_key()

    def _add_api_key(self, key_value=""):
        """添加 API Key 项"""
        index = len(self._api_key_items)
        item = ApiKeyItem(key_value, index)

        # 连接信号
        item.test_btn.clicked.connect(lambda checked, i=item: self._test_single_key(i))
        item.delete_btn.clicked.connect(lambda checked, i=item: self._remove_api_key(i))

        self._api_key_items.append(item)
        self.keys_layout.addWidget(item)

    def _remove_api_key(self, item):
        """删除 API Key 项"""
        if len(self._api_key_items) <= 1:
            InfoBar.warning(
                title="无法删除",
                content="至少需要保留一个 API Key",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
            return

        self._api_key_items.remove(item)
        self.keys_layout.removeWidget(item)
        item.deleteLater()

        # 更新索引
        for i, it in enumerate(self._api_key_items):
            it.set_index(i)

    def _get_all_keys(self):
        """获取所有 Key"""
        return [item.get_key() for item in self._api_key_items if item.get_key()]

    def _test_single_key(self, item):
        """测试单个 Key"""
        key = item.get_key()
        if not key:
            InfoBar.warning(
                title="Key 为空",
                content="请先输入 API Key",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
            return

        item.set_testing(True)
        item.status_label.setText("测试中...")

        # 后台测试
        from gui.utils.worker import Worker

        def test_func(progress_callback=None):
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage
            try:
                llm = ChatOpenAI(
                    model=self.doubao_model_edit.text().strip(),
                    base_url=self.doubao_base_edit.text().strip(),
                    api_key=key,
                    temperature=0.1,
                    timeout=30,
                )
                response = llm.invoke([HumanMessage(content='回复OK')])
                return True, "连接成功"
            except Exception as e:
                return False, str(e)[:50]

        worker = Worker(test_func)
        worker.finished_signal.connect(lambda result: self._on_single_key_test_finished(item, result))
        worker.error_signal.connect(lambda err: self._on_single_key_test_error(item, err))
        worker.start()
        self._test_workers.append(worker)

    def _on_single_key_test_finished(self, item, result):
        """单个 Key 测试完成"""
        success, message = result
        item.set_testing(False)
        item.set_status(success, message)

    def _on_single_key_test_error(self, item, error_msg):
        """单个 Key 测试出错"""
        item.set_testing(False)
        item.set_status(False, error_msg)

    def _test_all_doubao_keys(self):
        """测试所有 Key"""
        keys = self._get_all_keys()
        if not keys:
            InfoBar.warning(
                title="无 Key 配置",
                content="请先添加 API Key",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
            return

        # 设置所有项为测试中
        for item in self._api_key_items:
            if item.get_key():
                item.set_testing(True)
                item.status_label.setText("等待...")

        # 逐个测试（也可以改为并发）
        self._test_queue = [item for item in self._api_key_items if item.get_key()]
        self._test_next_key()

    def _test_next_key(self):
        """测试下一个 Key"""
        if not hasattr(self, '_test_queue') or not self._test_queue:
            return

        item = self._test_queue.pop(0)
        self._test_single_key(item)

        # 延迟测试下一个
        if self._test_queue:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(500, self._test_next_key)

    def _save_api_config(self):
        """保存API配置"""
        deepseek_key = self.deepseek_key_edit.text().strip()
        deepseek_base = self.deepseek_base_edit.text().strip()
        deepseek_model = self.deepseek_model_edit.text().strip()

        doubao_keys = self._get_all_keys()
        doubao_base = self.doubao_base_edit.text().strip()
        doubao_model = self.doubao_model_edit.text().strip()

        if not deepseek_key:
            InfoBar.warning(
                title="配置不完整",
                content="请输入 DeepSeek API Key",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        if not doubao_keys:
            InfoBar.warning(
                title="配置不完整",
                content="请至少添加一个 Doubao API Key",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        # 更新配置
        settings.deepseek_api_key = deepseek_key
        settings.deepseek_api_base = deepseek_base
        settings.deepseek_model = deepseek_model

        # 多 Key 配置
        settings.openai_api_keys = ",".join(doubao_keys)
        settings.openai_api_key = doubao_keys[0]  # 兼容旧配置
        settings.openai_api_base = doubao_base
        settings.doubao_model = doubao_model

        # 更新 LLM 服务配置
        llm_service.set_api_config(api_keys=doubao_keys, api_base=doubao_base, model=doubao_model)

        # 保存到.env文件
        env_path = get_app_dir() / ".env"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# 规则解析模型（纯文本）\n")
            f.write(f"DEEPSEEK_API_BASE={deepseek_base}\n")
            f.write(f"DEEPSEEK_API_KEY={deepseek_key}\n")
            f.write(f"DEEPSEEK_MODEL={deepseek_model}\n")
            f.write("\n# 海报分析模型（多模态）\n")
            # 保存多 Key
            for i, key in enumerate(doubao_keys):
                f.write(f"OPENAI_API_KEY_{i}={key}\n")
            f.write(f"OPENAI_API_BASE={doubao_base}\n")
            f.write(f"DOUBAO_MODEL={doubao_model}\n")

        InfoBar.success(
            title="保存成功",
            content=f"API 配置已保存（{len(doubao_keys)} 个 Key）",
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self
        )

    def _test_deepseek(self):
        """测试DeepSeek连接"""
        self.deepseek_test_btn.setEnabled(False)
        self.deepseek_test_btn.setText("测试中...")
        self.deepseek_status.setText("")

        # 先保存当前配置到settings
        settings.deepseek_api_key = self.deepseek_key_edit.text().strip()
        settings.deepseek_api_base = self.deepseek_base_edit.text().strip()
        settings.deepseek_model = self.deepseek_model_edit.text().strip()

        # 后台测试
        from gui.utils.worker import Worker

        self._test_worker = Worker(self._do_test_deepseek)
        self._test_worker.finished_signal.connect(self._on_deepseek_test_finished)
        self._test_worker.error_signal.connect(self._on_deepseek_test_error)
        self._test_worker.start()

    def _do_test_deepseek(self, progress_callback=None):
        """执行DeepSeek连接测试"""
        return llm_service.test_deepseek_connection()

    def _on_deepseek_test_finished(self, result):
        """DeepSeek测试完成"""
        success, message = result
        self.deepseek_test_btn.setEnabled(True)
        self.deepseek_test_btn.setText("测试连接")

        if success:
            self.deepseek_status.setStyleSheet("color: green;")
            self.deepseek_status.setText(f"✓ {message}")
        else:
            self.deepseek_status.setStyleSheet("color: red;")
            self.deepseek_status.setText(f"✗ {message}")

    def _on_deepseek_test_error(self, error_msg):
        """DeepSeek测试出错"""
        self.deepseek_test_btn.setEnabled(True)
        self.deepseek_test_btn.setText("测试连接")
        self.deepseek_status.setStyleSheet("color: red;")
        self.deepseek_status.setText(f"✗ {error_msg}")