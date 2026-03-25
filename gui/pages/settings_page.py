"""设置页面 - 配置API和品牌规范（Fluent风格）"""

import json
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog, QInputDialog, QLineEdit

from qfluentwidgets import (
    ScrollArea, SettingCardGroup,
    SettingCard, PushSettingCard, ComboBoxSettingCard,
    LineEdit, PasswordLineEdit, PushButton, PrimaryPushButton,
    ComboBox, TextEdit, StrongBodyLabel, CaptionLabel,
    InfoBar, InfoBarPosition, MessageBox, CardWidget,
    HeaderCardWidget, FluentIcon as FIF
)

from src.utils.config import settings, get_app_dir
from src.services.llm_service import llm_service
from src.services.rules_context import rules_context
from src.services.document_parser import document_parser
from gui.utils.worker import Worker


class SettingsPage(ScrollArea):
    """设置页面 - Fluent风格"""

    # 进度信号
    progress_updated = Signal(int, str, str)
    task_started = Signal(str)
    task_finished = Signal(bool, str)

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
        layout.setSpacing(28)

        # 标题
        title = StrongBodyLabel("系统设置")
        title.setStyleSheet("font-size: 24px;")
        layout.addWidget(title)

        # 规则解析模型配置组
        self._create_rules_model_group(layout)

        # 海报分析模型配置组
        self._create_audit_model_group(layout)

        # 规范管理组
        self._create_rules_management_group(layout)

        layout.addStretch()

    def _create_rules_model_group(self, parent_layout: QVBoxLayout):
        """创建规则解析模型配置组"""
        group = HeaderCardWidget("规则解析模型 (纯文本)", self.view)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(16)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # API Key
        key_layout = QHBoxLayout()
        key_label = StrongBodyLabel("API Key:")
        key_label.setFixedWidth(100)
        self.deepseek_key_edit = PasswordLineEdit()
        self.deepseek_key_edit.setPlaceholderText("DeepSeek API密钥...")
        self.deepseek_key_edit.setClearButtonEnabled(True)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.deepseek_key_edit)
        content_layout.addLayout(key_layout)

        # API Base
        base_layout = QHBoxLayout()
        base_label = StrongBodyLabel("API 地址:")
        base_label.setFixedWidth(100)
        self.deepseek_base_edit = LineEdit()
        self.deepseek_base_edit.setClearButtonEnabled(True)
        base_layout.addWidget(base_label)
        base_layout.addWidget(self.deepseek_base_edit)
        content_layout.addLayout(base_layout)

        # Model
        model_layout = QHBoxLayout()
        model_label = StrongBodyLabel("模型名称:")
        model_label.setFixedWidth(100)
        self.deepseek_model_edit = LineEdit()
        self.deepseek_model_edit.setClearButtonEnabled(True)
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.deepseek_model_edit)
        content_layout.addLayout(model_layout)

        group.viewLayout.addLayout(content_layout)
        parent_layout.addWidget(group)

    def _create_audit_model_group(self, parent_layout: QVBoxLayout):
        """创建海报分析模型配置组"""
        group = HeaderCardWidget("海报分析模型 (多模态)", self.view)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(16)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # API Key
        key_layout = QHBoxLayout()
        key_label = StrongBodyLabel("API Key:")
        key_label.setFixedWidth(100)
        self.doubao_key_edit = PasswordLineEdit()
        self.doubao_key_edit.setPlaceholderText("Doubao API密钥...")
        self.doubao_key_edit.setClearButtonEnabled(True)
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.doubao_key_edit)
        content_layout.addLayout(key_layout)

        # API Base
        base_layout = QHBoxLayout()
        base_label = StrongBodyLabel("API 地址:")
        base_label.setFixedWidth(100)
        self.doubao_base_edit = LineEdit()
        self.doubao_base_edit.setClearButtonEnabled(True)
        base_layout.addWidget(base_label)
        base_layout.addWidget(self.doubao_base_edit)
        content_layout.addLayout(base_layout)

        # Model
        model_layout = QHBoxLayout()
        model_label = StrongBodyLabel("模型名称:")
        model_label.setFixedWidth(100)
        self.doubao_model_edit = LineEdit()
        self.doubao_model_edit.setClearButtonEnabled(True)
        model_layout.addWidget(model_label)
        model_layout.addWidget(self.doubao_model_edit)
        content_layout.addLayout(model_layout)

        group.viewLayout.addLayout(content_layout)
        parent_layout.addWidget(group)

        # 保存按钮
        btn_layout = QHBoxLayout()
        save_btn = PrimaryPushButton("保存配置")
        save_btn.setMinimumWidth(150)
        save_btn.clicked.connect(self._save_api_config)
        btn_layout.addWidget(save_btn)
        btn_layout.addStretch()
        parent_layout.addLayout(btn_layout)

    def _create_rules_management_group(self, parent_layout: QVBoxLayout):
        """创建规范管理组"""
        group = HeaderCardWidget("品牌规范管理", self.view)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(16)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # 当前规范选择
        select_layout = QHBoxLayout()
        select_label = StrongBodyLabel("当前规范:")
        select_label.setFixedWidth(100)
        self.rules_combo = ComboBox()
        self.rules_combo.setMinimumWidth(350)
        select_layout.addWidget(select_label)
        select_layout.addWidget(self.rules_combo)
        select_layout.addStretch()
        content_layout.addLayout(select_layout)

        # 操作按钮行
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        delete_btn = PushButton("删除当前规范")
        delete_btn.clicked.connect(self._delete_rules)
        btn_layout.addWidget(delete_btn)

        self.upload_btn = PrimaryPushButton("上传规范文档 (PDF/PPT/Word/Excel/MD/TXT)")
        self.upload_btn.clicked.connect(self._upload_document)
        btn_layout.addWidget(self.upload_btn)
        btn_layout.addStretch()

        content_layout.addLayout(btn_layout)

        # 规范详情预览
        preview_label = StrongBodyLabel("规范详情预览:")
        content_layout.addWidget(preview_label)

        self.rules_preview = TextEdit()
        self.rules_preview.setReadOnly(True)
        self.rules_preview.setPlaceholderText("选择品牌规范后显示详情...")
        self.rules_preview.setMinimumHeight(300)
        content_layout.addWidget(self.rules_preview)

        group.viewLayout.addLayout(content_layout)
        parent_layout.addWidget(group)

        # 连接信号
        self.rules_combo.currentIndexChanged.connect(self._on_rules_changed)

        # 加载规范列表
        self._load_rules_list()

    def _load_settings(self):
        """加载设置"""
        # 规则解析模型配置
        self.deepseek_key_edit.setText(settings.deepseek_api_key)
        self.deepseek_base_edit.setText(settings.deepseek_api_base)
        self.deepseek_model_edit.setText(settings.deepseek_model)

        # 海报分析模型配置
        self.doubao_key_edit.setText(settings.openai_api_key)
        self.doubao_base_edit.setText(settings.openai_api_base)
        self.doubao_model_edit.setText(settings.doubao_model)

    def _save_api_config(self):
        """保存API配置"""
        # 获取规则解析模型配置
        deepseek_key = self.deepseek_key_edit.text().strip()
        deepseek_base = self.deepseek_base_edit.text().strip()
        deepseek_model = self.deepseek_model_edit.text().strip()

        # 获取海报分析模型配置
        doubao_key = self.doubao_key_edit.text().strip()
        doubao_base = self.doubao_base_edit.text().strip()
        doubao_model = self.doubao_model_edit.text().strip()

        if not deepseek_key:
            InfoBar.warning(
                title="警告",
                content="请输入规则解析模型的 API Key",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        if not doubao_key:
            InfoBar.warning(
                title="警告",
                content="请输入海报分析模型的 API Key",
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
            title="成功",
            content="API配置已保存",
            position=InfoBarPosition.TOP,
            duration=2000,
            parent=self
        )

    def _load_rules_list(self):
        """加载规范列表"""
        self.rules_combo.clear()

        rules_list = rules_context.list_rules()
        for rule in rules_list:
            brand_id = rule.get("brand_id", "")
            brand_name = rule.get("brand_name", "未命名")
            self.rules_combo.addItem(f"{brand_name} ({brand_id})", userData=brand_id)

        if self.rules_combo.count() == 0:
            self.rules_combo.addItem("暂无规范", userData="")

        self._on_rules_changed()

    def _on_rules_changed(self):
        """规范选择变化"""
        brand_id = self.rules_combo.currentData()
        if brand_id:
            rules = rules_context.get_rules(brand_id)
            if rules:
                # 格式化显示规范详情
                self.rules_preview.setPlainText(self._format_rules_detail(rules))
            rules_context.set_current_brand(brand_id)
        else:
            self.rules_preview.clear()

    def _format_rules_detail(self, rules) -> str:
        """格式化规范详情显示"""
        lines = [f"品牌名称: {rules.brand_name}", f"版本: {rules.version}", ""]

        has_structured_rules = False

        # 色彩规范
        if rules.color and (rules.color.primary or rules.color.secondary or rules.color.forbidden):
            has_structured_rules = True
            lines.append("【色彩规范】")
            if rules.color.primary:
                lines.append(f"  主色: {rules.color.primary.value} ({rules.color.primary.name})")
            if rules.color.secondary:
                colors = ", ".join(f"{c.value} ({c.name})" for c in rules.color.secondary)
                lines.append(f"  辅助色: {colors}")
            if rules.color.forbidden:
                colors = ", ".join(f"{c.value}" for c in rules.color.forbidden)
                lines.append(f"  禁用色: {colors}")
            lines.append("")

        # Logo规范
        if rules.logo and (rules.logo.position_description or rules.logo.size_range):
            has_structured_rules = True
            lines.append("【Logo规范】")
            lines.append(f"  位置: {rules.logo.position_description}")
            if rules.logo.size_range:
                lines.append(f"  尺寸: {rules.logo.size_range.get('min', 5)}% - {rules.logo.size_range.get('max', 15)}%")
            lines.append(f"  安全间距: {rules.logo.safe_margin_px}px")
            lines.append("")

        # 字体规范
        if rules.font and (rules.font.allowed or rules.font.forbidden):
            has_structured_rules = True
            lines.append("【字体规范】")
            if rules.font.allowed:
                lines.append(f"  允许: {', '.join(rules.font.allowed)}")
            if rules.font.forbidden:
                lines.append(f"  禁用: {', '.join(rules.font.forbidden)}")
            lines.append("")

        # 文案规范
        if rules.copywriting and rules.copywriting.forbidden_words:
            has_structured_rules = True
            lines.append("【文案规范】")
            words = ", ".join(w.word for w in rules.copywriting.forbidden_words)
            lines.append(f"  禁用词: {words}")
            lines.append("")

        # 布局规范
        if rules.layout and rules.layout.margin_min:
            has_structured_rules = True
            lines.append("【布局规范】")
            lines.append(f"  最小边距: {rules.layout.margin_min}px")
            if rules.layout.description:
                lines.append(f"  说明: {rules.layout.description}")

        # 如果没有结构化规则，显示原始文本
        if not has_structured_rules and rules.raw_text:
            lines.append("【原始规范文本】")
            lines.append("")
            # 截取前3000字符显示
            text = rules.raw_text[:3000]
            if len(rules.raw_text) > 3000:
                text += f"\n\n... (共 {len(rules.raw_text)} 字符，已截取前3000字)"
            lines.append(text)

        return "\n".join(lines)

    def _upload_document(self):
        """上传规范文档"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择规范文档", "",
            "支持的文件 (*.pdf *.pptx *.ppt *.docx *.doc *.xlsx *.xls *.md *.txt);;"
            "PDF文档 (*.pdf);;"
            "PowerPoint演示文稿 (*.pptx *.ppt);;"
            "Word文档 (*.docx *.doc);;"
            "Excel表格 (*.xlsx *.xls);;"
            "Markdown文档 (*.md);;"
            "文本文件 (*.txt);;"
            "所有文件 (*.*)"
        )

        if not file_path:
            return

        # 从文件名提取默认品牌名（去掉扩展名）
        file_name = Path(file_path).stem
        default_name = file_name[:20] if len(file_name) > 20 else file_name  # 限制长度

        # 弹出输入对话框让用户命名
        brand_name, ok = QInputDialog.getText(
            self, "品牌命名",
            "请输入品牌名称（留空则自动从文件名提取）:",
            QLineEdit.EchoMode.Normal,
            default_name
        )

        if not ok:
            # 用户取消
            return

        # 如果用户输入为空，使用默认名称
        brand_name = brand_name.strip() if brand_name.strip() else default_name

        # 发送任务开始信号
        self.task_started.emit("规范文档解析")
        self.progress_updated.emit(-1, "正在读取文档...", f"开始解析: {Path(file_path).name}")

        # 禁用按钮，显示处理中
        self.upload_btn.setEnabled(False)
        self.upload_btn.setText("解析中...")
        self._current_brand_name = brand_name  # 保存品牌名称

        # 后台线程解析
        self._parse_worker = Worker(self._parse_with_progress, file_path, brand_name)
        self._parse_worker.finished_signal.connect(self._on_parse_finished)
        self._parse_worker.error_signal.connect(self._on_parse_error)
        self._parse_worker.progress_signal.connect(lambda p, m: self.progress_updated.emit(p, m, m))
        self._parse_worker.start()

    def _parse_with_progress(self, file_path: str, brand_name: str, progress_callback=None):
        """带进度回调的文档解析"""
        self.progress_updated.emit(20, "正在提取文档内容...", "")
        result = document_parser.parse_file(file_path, brand_name)
        self.progress_updated.emit(80, "正在解析规范结构...", "")
        return result

    def _on_parse_finished(self, rules):
        """解析完成"""
        self.upload_btn.setEnabled(True)
        self.upload_btn.setText("上传规范文档 (PDF/PPT/Word/Excel/MD/TXT)")

        # 使用用户输入的品牌名称
        if hasattr(self, '_current_brand_name') and self._current_brand_name:
            rules.brand_name = self._current_brand_name

        # 保存
        brand_id = rules_context.add_rules(rules)

        # 发送任务完成信号
        self.task_finished.emit(True, f"规范文档解析完成: {rules.brand_name}")

        InfoBar.success(
            title="成功",
            content=f"规范文档已解析并保存\n品牌: {rules.brand_name}\nID: {brand_id}",
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )

        self._load_rules_list()

    def _on_parse_error(self, error_msg):
        """解析失败"""
        self.upload_btn.setEnabled(True)
        self.upload_btn.setText("上传规范文档 (PDF/PPT/Word/Excel/MD/TXT)")

        # 发送任务失败信号
        self.task_finished.emit(False, f"解析失败: {error_msg}")

        InfoBar.error(
            title="错误",
            content=f"解析失败: {error_msg}",
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _delete_rules(self):
        """删除规范"""
        brand_id = self.rules_combo.currentData()
        if not brand_id:
            InfoBar.warning(
                title="警告",
                content="请选择要删除的规范",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        box = MessageBox(
            "确认删除",
            f"确定要删除规范 '{self.rules_combo.currentText()}' 吗？",
            self
        )
        box.yesButton.setText("确定")
        box.cancelButton.setText("取消")

        if box.exec():
            rules_context.delete_rules(brand_id)
            self._load_rules_list()
            InfoBar.success(
                title="成功",
                content="规范已删除",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )