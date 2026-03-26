"""设置页面 - API配置（Fluent风格）"""

from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    ScrollArea, StrongBodyLabel, CaptionLabel,
    LineEdit, PasswordLineEdit, PrimaryPushButton, PushButton,
    InfoBar, InfoBarPosition, CardWidget, TitleLabel, FluentIcon as FIF
)

from src.utils.config import settings, get_app_dir
from src.services.llm_service import llm_service


class SettingsPage(ScrollArea):
    """设置页面 - Fluent风格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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
        key_label.setFixedWidth(100)
        self.deepseek_key_edit = PasswordLineEdit()
        self.deepseek_key_edit.setPlaceholderText("输入 DeepSeek API 密钥...")
        self.deepseek_key_edit.setClearButtonEnabled(True)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.deepseek_key_edit)
        rules_layout.addLayout(key_layout)

        # API Base
        base_layout = QHBoxLayout()
        base_label = StrongBodyLabel("API 地址")
        base_label.setFixedWidth(100)
        self.deepseek_base_edit = LineEdit()
        self.deepseek_base_edit.setPlaceholderText("https://api.deepseek.com")
        self.deepseek_base_edit.setClearButtonEnabled(True)
        base_layout.addWidget(base_label)
        base_layout.addWidget(self.deepseek_base_edit)
        rules_layout.addLayout(base_layout)

        # Model
        model_layout = QHBoxLayout()
        model_label = StrongBodyLabel("模型名称")
        model_label.setFixedWidth(100)
        self.deepseek_model_edit = LineEdit()
        self.deepseek_model_edit.setPlaceholderText("deepseek-chat")
        self.deepseek_model_edit.setClearButtonEnabled(True)
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.deepseek_model_edit)
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

        # 海报分析模型配置卡片
        audit_card = CardWidget()
        audit_card.setBorderRadius(12)
        audit_layout = QVBoxLayout(audit_card)
        audit_layout.setContentsMargins(24, 20, 24, 24)
        audit_layout.setSpacing(16)

        audit_title = StrongBodyLabel("海报分析模型 (Doubao/豆包)")
        audit_desc = CaptionLabel("用于审核设计图片，需要多模态视觉能力")
        audit_layout.addWidget(audit_title)
        audit_layout.addWidget(audit_desc)

        # API Key
        key_layout2 = QHBoxLayout()
        key_label2 = StrongBodyLabel("API Key")
        key_label2.setFixedWidth(100)
        self.doubao_key_edit = PasswordLineEdit()
        self.doubao_key_edit.setPlaceholderText("输入 Doubao API 密钥...")
        self.doubao_key_edit.setClearButtonEnabled(True)
        key_layout2.addWidget(key_label2)
        key_layout2.addWidget(self.doubao_key_edit)
        audit_layout.addLayout(key_layout2)

        # API Base
        base_layout2 = QHBoxLayout()
        base_label2 = StrongBodyLabel("API 地址")
        base_label2.setFixedWidth(100)
        self.doubao_base_edit = LineEdit()
        self.doubao_base_edit.setPlaceholderText("https://ark.cn-beijing.volces.com/api/v3")
        self.doubao_base_edit.setClearButtonEnabled(True)
        base_layout2.addWidget(base_label2)
        base_layout2.addWidget(self.doubao_base_edit)
        audit_layout.addLayout(base_layout2)

        # Model
        model_layout2 = QHBoxLayout()
        model_label2 = StrongBodyLabel("模型名称")
        model_label2.setFixedWidth(100)
        self.doubao_model_edit = LineEdit()
        self.doubao_model_edit.setPlaceholderText("doubao-vision-pro-32k")
        self.doubao_model_edit.setClearButtonEnabled(True)
        model_layout2.addWidget(model_label2)
        model_layout2.addWidget(self.doubao_model_edit)
        audit_layout.addLayout(model_layout2)

        # 测试按钮行
        test_layout2 = QHBoxLayout()
        self.doubao_test_btn = PushButton("测试连接")
        self.doubao_test_btn.setIcon(FIF.PLAY)
        self.doubao_test_btn.clicked.connect(self._test_doubao)
        test_layout2.addWidget(self.doubao_test_btn)

        self.doubao_status = CaptionLabel("")
        test_layout2.addWidget(self.doubao_status)
        test_layout2.addStretch()
        audit_layout.addLayout(test_layout2)

        layout.addWidget(audit_card)

        # 保存按钮
        btn_layout = QHBoxLayout()
        save_btn = PrimaryPushButton("保存配置")
        save_btn.setMinimumWidth(150)
        save_btn.clicked.connect(self._save_api_config)
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

    def _load_settings(self):
        """加载设置"""
        self.deepseek_key_edit.setText(settings.deepseek_api_key)
        self.deepseek_base_edit.setText(settings.deepseek_api_base)
        self.deepseek_model_edit.setText(settings.deepseek_model)

        self.doubao_key_edit.setText(settings.openai_api_key)
        self.doubao_base_edit.setText(settings.openai_api_base)
        self.doubao_model_edit.setText(settings.doubao_model)

    def _save_api_config(self):
        """保存API配置"""
        deepseek_key = self.deepseek_key_edit.text().strip()
        deepseek_base = self.deepseek_base_edit.text().strip()
        deepseek_model = self.deepseek_model_edit.text().strip()

        doubao_key = self.doubao_key_edit.text().strip()
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

        if not doubao_key:
            InfoBar.warning(
                title="配置不完整",
                content="请输入 Doubao API Key",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        # 更新配置
        settings.deepseek_api_key = deepseek_key
        settings.deepseek_api_base = deepseek_base
        settings.deepseek_model = deepseek_model

        settings.openai_api_key = doubao_key
        settings.openai_api_base = doubao_base
        settings.doubao_model = doubao_model

        # 更新 LLM 服务配置
        llm_service.set_api_config(doubao_key, doubao_base, doubao_model)

        # 保存到.env文件
        env_path = get_app_dir() / ".env"
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("# 规则解析模型（纯文本）\n")
            f.write(f"DEEPSEEK_API_BASE={deepseek_base}\n")
            f.write(f"DEEPSEEK_API_KEY={deepseek_key}\n")
            f.write(f"DEEPSEEK_MODEL={deepseek_model}\n")
            f.write("\n# 海报分析模型（多模态）\n")
            f.write(f"OPENAI_API_KEY={doubao_key}\n")
            f.write(f"OPENAI_API_BASE={doubao_base}\n")
            f.write(f"DOUBAO_MODEL={doubao_model}\n")

        InfoBar.success(
            title="保存成功",
            content="API 配置已保存",
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

        def do_test():
            return llm_service.test_deepseek_connection()

        self._test_worker = Worker(do_test)
        self._test_worker.finished_signal.connect(
            lambda result: self._on_deepseek_test_finished(result)
        )
        self._test_worker.start()

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

    def _test_doubao(self):
        """测试Doubao连接"""
        self.doubao_test_btn.setEnabled(False)
        self.doubao_test_btn.setText("测试中...")
        self.doubao_status.setText("")

        # 先保存当前配置到settings
        settings.openai_api_key = self.doubao_key_edit.text().strip()
        settings.openai_api_base = self.doubao_base_edit.text().strip()
        settings.doubao_model = self.doubao_model_edit.text().strip()

        # 后台测试
        from gui.utils.worker import Worker

        def do_test():
            return llm_service.test_doubao_connection()

        self._test_worker2 = Worker(do_test)
        self._test_worker2.finished_signal.connect(
            lambda result: self._on_doubao_test_finished(result)
        )
        self._test_worker2.start()

    def _on_doubao_test_finished(self, result):
        """Doubao测试完成"""
        success, message = result
        self.doubao_test_btn.setEnabled(True)
        self.doubao_test_btn.setText("测试连接")

        if success:
            self.doubao_status.setStyleSheet("color: green;")
            self.doubao_status.setText(f"✓ {message}")
        else:
            self.doubao_status.setStyleSheet("color: red;")
            self.doubao_status.setText(f"✗ {message}")