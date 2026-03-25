"""设置页面 - 配置API和品牌规范"""

import json
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QGroupBox, QFileDialog, QMessageBox, QTextEdit, QComboBox, QTabWidget,
    QScrollArea, QFrame, QGridLayout, QInputDialog, QSizePolicy, QSplitter
)
from PySide6.QtCore import Qt

from src.utils.config import settings, get_app_dir
from src.services.llm_service import llm_service
from src.services.rules_context import rules_context
from src.services.document_parser import document_parser
from gui.utils.worker import Worker


class SettingsPage(QWidget):
    """设置页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        # 标题
        title = QLabel("系统设置")
        title.setStyleSheet("font-size: 26px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 标签页
        tab_widget = QTabWidget()
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                border-radius: 8px;
                background-color: white;
                font-size: 15px;
            }
            QTabBar::tab {
                padding: 12px 30px;
                margin-right: 2px;
                background-color: #ecf0f1;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-size: 15px;
            }
            QTabBar::tab:selected {
                background-color: white;
                font-weight: bold;
            }
        """)

        # API配置标签
        api_tab = self._create_api_tab()
        tab_widget.addTab(api_tab, "API配置")

        # 规范管理标签
        rules_tab = self._create_rules_tab()
        tab_widget.addTab(rules_tab, "规范管理")

        layout.addWidget(tab_widget)

    def _create_api_tab(self) -> QWidget:
        """创建API配置标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(25)

        # 规则解析模型配置组（DeepSeek - 纯文本）
        rules_model_group = QGroupBox("规则解析模型 (纯文本)")
        rules_model_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        rules_layout = QGridLayout(rules_model_group)
        rules_layout.setSpacing(15)

        # DeepSeek API Key
        deepseek_key_label = QLabel("API Key:")
        deepseek_key_label.setStyleSheet("font-size: 14px;")
        rules_layout.addWidget(deepseek_key_label, 0, 0)
        self.deepseek_key_edit = QLineEdit()
        self.deepseek_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepseek_key_edit.setPlaceholderText("DeepSeek API密钥...")
        self.deepseek_key_edit.setMinimumWidth(450)
        rules_layout.addWidget(self.deepseek_key_edit, 0, 1)

        # DeepSeek API Base
        deepseek_base_label = QLabel("API 地址:")
        deepseek_base_label.setStyleSheet("font-size: 14px;")
        rules_layout.addWidget(deepseek_base_label, 1, 0)
        self.deepseek_base_edit = QLineEdit()
        rules_layout.addWidget(self.deepseek_base_edit, 1, 1)

        # DeepSeek Model
        deepseek_model_label = QLabel("模型名称:")
        deepseek_model_label.setStyleSheet("font-size: 14px;")
        rules_layout.addWidget(deepseek_model_label, 2, 0)
        self.deepseek_model_edit = QLineEdit()
        rules_layout.addWidget(self.deepseek_model_edit, 2, 1)

        layout.addWidget(rules_model_group)

        # 海报分析模型配置组（Doubao - 多模态）
        audit_model_group = QGroupBox("海报分析模型 (多模态)")
        audit_model_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        audit_layout = QGridLayout(audit_model_group)
        audit_layout.setSpacing(15)

        # Doubao API Key
        doubao_key_label = QLabel("API Key:")
        doubao_key_label.setStyleSheet("font-size: 14px;")
        audit_layout.addWidget(doubao_key_label, 0, 0)
        self.doubao_key_edit = QLineEdit()
        self.doubao_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.doubao_key_edit.setPlaceholderText("Doubao API密钥...")
        self.doubao_key_edit.setMinimumWidth(450)
        audit_layout.addWidget(self.doubao_key_edit, 0, 1)

        # Doubao API Base
        doubao_base_label = QLabel("API 地址:")
        doubao_base_label.setStyleSheet("font-size: 14px;")
        audit_layout.addWidget(doubao_base_label, 1, 0)
        self.doubao_base_edit = QLineEdit()
        audit_layout.addWidget(self.doubao_base_edit, 1, 1)

        # Doubao Model
        doubao_model_label = QLabel("模型名称:")
        doubao_model_label.setStyleSheet("font-size: 14px;")
        audit_layout.addWidget(doubao_model_label, 2, 0)
        self.doubao_model_edit = QLineEdit()
        audit_layout.addWidget(self.doubao_model_edit, 2, 1)

        layout.addWidget(audit_model_group)

        # 保存按钮
        save_api_btn = QPushButton("保存配置")
        save_api_btn.setMinimumWidth(150)
        save_api_btn.clicked.connect(self._save_api_config)
        save_api_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 12px 40px;
                border: none;
                border-radius: 5px;
                font-size: 15px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        layout.addWidget(save_api_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addStretch()

        return widget

    def _create_rules_tab(self) -> QWidget:
        """创建规范管理标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 使用QSplitter实现可调整大小的面板
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #ddd;
                width: 3px;
            }
        """)

        # 左侧：规范列表
        left_panel = QFrame()
        left_panel.setStyleSheet("QFrame { background-color: white; border-radius: 8px; }")
        left_panel.setMinimumWidth(350)

        # 创建滚动区域包裹左侧内容
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        left_content = QWidget()
        left_layout = QVBoxLayout(left_content)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(15)

        list_title = QLabel("已导入的规范")
        list_title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        left_layout.addWidget(list_title)

        # 规范选择下拉
        select_layout = QHBoxLayout()
        select_label = QLabel("当前规范:")
        select_label.setStyleSheet("font-size: 15px;")
        select_layout.addWidget(select_label)
        self.rules_combo = QComboBox()
        self.rules_combo.setMinimumWidth(300)
        self.rules_combo.setStyleSheet("""
            QComboBox {
                font-size: 15px;
                padding: 8px;
                background-color: white;
                color: #2c3e50;
                border: 1px solid #bdc3c7;
                border-radius: 4px;
            }
            QComboBox:hover {
                border: 1px solid #3498db;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: #2c3e50;
                selection-background-color: #3498db;
                selection-color: white;
                font-size: 15px;
            }
        """)
        select_layout.addWidget(self.rules_combo)
        left_layout.addLayout(select_layout)

        # 刷新和设为当前按钮
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("刷新列表")
        refresh_btn.setStyleSheet("font-size: 15px; padding: 8px 16px;")
        refresh_btn.clicked.connect(self._load_rules_list)
        btn_row.addWidget(refresh_btn)

        set_current_btn = QPushButton("设为当前")
        set_current_btn.setStyleSheet("font-size: 15px; padding: 8px 16px;")
        set_current_btn.clicked.connect(self._set_current_brand)
        btn_row.addWidget(set_current_btn)

        delete_btn = QPushButton("删除")
        delete_btn.setStyleSheet("background-color: #e74c3c; color: white; font-size: 15px; padding: 8px 16px;")
        delete_btn.clicked.connect(self._delete_rules)
        btn_row.addWidget(delete_btn)

        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        # 上传按钮
        upload_row = QHBoxLayout()
        self.upload_btn = QPushButton("上传规范文档 (PDF/PPT/Word/Excel/MD/TXT)")
        self.upload_btn.setMinimumHeight(50)
        self.upload_btn.clicked.connect(self._upload_document)
        self.upload_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-size: 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
        """)
        upload_row.addWidget(self.upload_btn)

        self.new_btn = QPushButton("新建空白规范")
        self.new_btn.setMinimumHeight(50)
        self.new_btn.setStyleSheet("font-size: 15px;")
        self.new_btn.clicked.connect(self._new_rules)
        upload_row.addWidget(self.new_btn)
        left_layout.addLayout(upload_row)

        left_layout.addStretch()

        # 将左侧内容添加到滚动区域
        left_scroll.setWidget(left_content)
        splitter.addWidget(left_scroll)

        # 右侧：规范详情
        right_panel = QFrame()
        right_panel.setStyleSheet("QFrame { background-color: white; border-radius: 8px; }")
        right_panel.setMinimumWidth(400)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)

        detail_title = QLabel("规范详情")
        detail_title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        right_layout.addWidget(detail_title)

        # 规范预览
        self.rules_preview = QTextEdit()
        self.rules_preview.setReadOnly(True)
        self.rules_preview.setPlaceholderText("选择品牌规范后显示详情...")
        self.rules_preview.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ddd;
                border-radius: 5px;
                padding: 15px;
                font-size: 14px;
                line-height: 1.6;
            }
        """)
        right_layout.addWidget(self.rules_preview)

        splitter.addWidget(right_panel)

        # 设置初始比例
        splitter.setSizes([350, 600])

        layout.addWidget(splitter)

        # 连接信号
        self.rules_combo.currentIndexChanged.connect(self._on_rules_changed)

        # 加载规范列表
        self._load_rules_list()

        return widget

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
            QMessageBox.warning(self, "警告", "请输入规则解析模型的 API Key")
            return

        if not doubao_key:
            QMessageBox.warning(self, "警告", "请输入海报分析模型的 API Key")
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

        QMessageBox.information(self, "成功", "API配置已保存")

    def _load_rules_list(self):
        """加载规范列表"""
        self.rules_combo.clear()

        rules_list = rules_context.list_rules()
        for rule in rules_list:
            brand_id = rule.get("brand_id", "")
            brand_name = rule.get("brand_name", "未命名")
            self.rules_combo.addItem(f"{brand_name} ({brand_id})", brand_id)

        if self.rules_combo.count() == 0:
            self.rules_combo.addItem("暂无规范", "")

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

    def _set_current_brand(self):
        """设为当前品牌"""
        brand_id = self.rules_combo.currentData()
        if brand_id:
            rules_context.set_current_brand(brand_id)
            brand_name = self.rules_combo.currentText().split(" (")[0]
            QMessageBox.information(self, "成功", f"已切换到品牌: {brand_name}")
        else:
            QMessageBox.warning(self, "警告", "请选择一个品牌规范")

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

        # 禁用按钮，显示处理中
        self.upload_btn.setEnabled(False)
        self.upload_btn.setText("解析中...")
        self._current_brand_name = brand_name  # 保存品牌名称

        # 后台线程解析
        self._parse_worker = Worker(document_parser.parse_file, file_path, brand_name)
        self._parse_worker.finished_signal.connect(self._on_parse_finished)
        self._parse_worker.error_signal.connect(self._on_parse_error)
        self._parse_worker.start()

    def _on_parse_finished(self, rules):
        """解析完成"""
        self.upload_btn.setEnabled(True)
        self.upload_btn.setText("上传规范文档 (PDF/PPT/Word/Excel/MD/TXT)")

        # 使用用户输入的品牌名称
        if hasattr(self, '_current_brand_name') and self._current_brand_name:
            rules.brand_name = self._current_brand_name

        # 保存
        brand_id = rules_context.add_rules(rules)

        QMessageBox.information(
            self, "成功",
            f"规范文档已解析并保存\n品牌: {rules.brand_name}\nID: {brand_id}"
        )

        self._load_rules_list()

    def _on_parse_error(self, error_msg):
        """解析失败"""
        self.upload_btn.setEnabled(True)
        self.upload_btn.setText("上传规范文档 (PDF/PPT/Word/Excel/MD/TXT)")
        QMessageBox.critical(self, "错误", f"解析失败: {error_msg}")

    def _new_rules(self):
        """新建空白规范"""
        from src.models.schemas import BrandRules

        rules = BrandRules(
            brand_id="",
            brand_name="新品牌",
            version="1.0",
        )

        brand_id = rules_context.add_rules(rules)

        QMessageBox.information(self, "成功", f"已创建空白规范: {brand_id}")
        self._load_rules_list()

    def _delete_rules(self):
        """删除规范"""
        brand_id = self.rules_combo.currentData()
        if not brand_id:
            QMessageBox.warning(self, "警告", "请选择要删除的规范")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除规范 '{self.rules_combo.currentText()}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            rules_context.delete_rules(brand_id)
            self._load_rules_list()
            QMessageBox.information(self, "成功", "规范已删除")