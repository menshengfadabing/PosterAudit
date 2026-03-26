"""规范管理页面（Fluent风格）"""

import json
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QInputDialog, QLineEdit

from qfluentwidgets import (
    ScrollArea, StrongBodyLabel, CaptionLabel, BodyLabel,
    PushButton, PrimaryPushButton, ComboBox, TextEdit,
    InfoBar, InfoBarPosition, MessageBox, CardWidget,
    TitleLabel, FluentIcon as FIF, IconWidget
)

from src.utils.config import get_app_dir
from src.services.rules_context import rules_context
from src.services.document_parser import document_parser
from gui.utils.worker import Worker


class RulesPage(ScrollArea):
    """规范管理页面 - Fluent风格"""

    # 进度信号
    progress_updated = Signal(int, str, str)
    task_started = Signal(str)
    task_finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rulesPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._init_ui()
        self._load_rules_list()

    def _init_ui(self):
        # 主容器
        self.view = QWidget()
        self.setWidget(self.view)

        layout = QVBoxLayout(self.view)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(20)

        # 标题区域
        header_layout = QHBoxLayout()
        title = TitleLabel("品牌规范管理")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # 上传按钮
        self.upload_btn = PrimaryPushButton("上传规范文档")
        self.upload_btn.setIcon(FIF.ADD)
        self.upload_btn.clicked.connect(self._upload_document)
        header_layout.addWidget(self.upload_btn)

        layout.addLayout(header_layout)

        # 说明
        desc = CaptionLabel("管理品牌合规规范文档，支持 PDF、PPT、Word、Excel、Markdown 等格式")
        layout.addWidget(desc)

        # 主内容区
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # 左侧：规范列表
        left_card = CardWidget()
        left_card.setMinimumWidth(380)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(16)

        # 当前规范选择
        select_title = StrongBodyLabel("当前使用的规范")
        left_layout.addWidget(select_title)

        select_layout = QHBoxLayout()
        self.rules_combo = ComboBox()
        self.rules_combo.setMinimumWidth(300)
        self.rules_combo.currentIndexChanged.connect(self._on_rules_changed)
        select_layout.addWidget(self.rules_combo)
        select_layout.addStretch()
        left_layout.addLayout(select_layout)

        # 规范信息卡片
        info_card = CardWidget()
        info_card.setBorderRadius(8)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 16, 16, 16)
        info_layout.setSpacing(8)

        self.brand_name_label = BodyLabel("品牌名称: --")
        info_layout.addWidget(self.brand_name_label)
        left_layout.addWidget(info_card)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        self.delete_btn = PushButton("删除当前规范")
        self.delete_btn.setIcon(FIF.DELETE)
        self.delete_btn.clicked.connect(self._delete_rules)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()
        left_layout.addLayout(btn_layout)

        left_layout.addStretch()
        content_layout.addWidget(left_card, 1)

        # 右侧：规范详情
        right_card = CardWidget()
        right_card.setMinimumWidth(500)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)

        detail_title = StrongBodyLabel("规范详情预览")
        right_layout.addWidget(detail_title)

        # 导出按钮行
        export_layout = QHBoxLayout()
        self.export_json_btn = PushButton("导出JSON")
        self.export_json_btn.setIcon(FIF.SAVE)
        self.export_json_btn.clicked.connect(self._export_json)
        export_layout.addWidget(self.export_json_btn)

        self.export_md_btn = PushButton("导出Markdown")
        self.export_md_btn.setIcon(FIF.DOCUMENT)
        self.export_md_btn.clicked.connect(self._export_markdown)
        export_layout.addWidget(self.export_md_btn)

        export_layout.addStretch()
        right_layout.addLayout(export_layout)

        # 规范预览
        self.rules_preview = TextEdit()
        self.rules_preview.setReadOnly(True)
        self.rules_preview.setPlaceholderText("选择品牌规范后显示详情...")
        right_layout.addWidget(self.rules_preview)

        content_layout.addWidget(right_card, 1)

        layout.addLayout(content_layout, 1)

    def _load_rules_list(self):
        """加载规范列表"""
        self.rules_combo.clear()

        rules_list = rules_context.list_rules()
        for rule in rules_list:
            brand_id = rule.get("brand_id", "")
            brand_name = rule.get("brand_name", "未命名")
            self.rules_combo.addItem(f"{brand_name} ({brand_id})", userData=brand_id)

        if self.rules_combo.count() == 0:
            self.rules_combo.addItem("暂无规范，请上传", userData="")

        self._on_rules_changed()

    def _on_rules_changed(self):
        """规范选择变化"""
        brand_id = self.rules_combo.currentData()
        if brand_id:
            rules = rules_context.get_rules(brand_id)
            if rules:
                # 更新信息
                self.brand_name_label.setText(f"品牌名称: {rules.brand_name}")

                # 格式化显示规范详情
                self.rules_preview.setPlainText(self._format_rules_detail(rules))

                rules_context.set_current_brand(brand_id)
            else:
                self._clear_info()
        else:
            self._clear_info()

    def _clear_info(self):
        """清空信息"""
        self.brand_name_label.setText("品牌名称: --")
        self.rules_preview.clear()

    def _format_rules_detail(self, rules) -> str:
        """格式化规范详情显示"""
        lines = [f"品牌名称: {rules.brand_name}", ""]

        # === 主要规范 ===
        has_primary_rules = False

        # 色彩规范
        if rules.color and (rules.color.primary or rules.color.secondary or rules.color.forbidden):
            has_primary_rules = True
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
            has_primary_rules = True
            lines.append("【Logo规范】")
            lines.append(f"  位置: {rules.logo.position_description}")
            if rules.logo.size_range:
                lines.append(f"  尺寸: {rules.logo.size_range.get('min', 5)}% - {rules.logo.size_range.get('max', 15)}%")
            lines.append(f"  安全间距: {rules.logo.safe_margin_px}px")
            lines.append("")

        # 字体规范
        if rules.font and (rules.font.allowed or rules.font.forbidden):
            has_primary_rules = True
            lines.append("【字体规范】")
            if rules.font.allowed:
                lines.append(f"  允许: {', '.join(rules.font.allowed)}")
            if rules.font.forbidden:
                lines.append(f"  禁用: {', '.join(rules.font.forbidden)}")
            lines.append("")

        if not has_primary_rules:
            lines.append("【主要规范】暂无")
            lines.append("")

        # === 次要规范 ===
        if hasattr(rules, 'secondary_rules') and rules.secondary_rules:
            lines.append("【次要规范】")

            # 按分类分组
            categories = {}
            for rule in rules.secondary_rules:
                if rule.category not in categories:
                    categories[rule.category] = []
                categories[rule.category].append(rule)

            for category, rules_list in categories.items():
                lines.append(f"  {category}:")
                for rule in sorted(rules_list, key=lambda x: x.priority):
                    lines.append(f"    - {rule.name}: {rule.content}")
            lines.append("")
        else:
            lines.append("【次要规范】暂无")
            lines.append("")

        return "\n".join(lines)

    def _export_json(self):
        """导出规范为JSON"""
        brand_id = self.rules_combo.currentData()
        if not brand_id:
            InfoBar.warning(
                title="警告",
                content="请先选择要导出的规范",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        rules = rules_context.get_rules(brand_id)
        if not rules:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出JSON",
            f"{rules.brand_name}_规范.json",
            "JSON文件 (*.json)"
        )

        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(rules.to_json())

            InfoBar.success(
                title="导出成功",
                content=f"已导出到: {file_path}",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _export_markdown(self):
        """导出规范为Markdown"""
        brand_id = self.rules_combo.currentData()
        if not brand_id:
            InfoBar.warning(
                title="警告",
                content="请先选择要导出的规范",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        rules = rules_context.get_rules(brand_id)
        if not rules:
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出Markdown",
            f"{rules.brand_name}_规范.md",
            "Markdown文件 (*.md)"
        )

        if file_path:
            md_content = self._rules_to_markdown(rules)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(md_content)

            InfoBar.success(
                title="导出成功",
                content=f"已导出到: {file_path}",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

    def _rules_to_markdown(self, rules) -> str:
        """将规范转换为Markdown格式"""
        lines = [f"# {rules.brand_name} 品牌规范", ""]

        # 主要规范
        lines.append("## 主要规范")
        lines.append("")

        # 色彩规范
        if rules.color:
            lines.append("### 色彩规范")
            if rules.color.primary:
                lines.append(f"- **主色**: {rules.color.primary.value} ({rules.color.primary.name})")
            if rules.color.secondary:
                lines.append("- **辅助色**:")
                for c in rules.color.secondary:
                    lines.append(f"  - {c.value} ({c.name})")
            if rules.color.forbidden:
                lines.append("- **禁用色**:")
                for c in rules.color.forbidden:
                    reason = f" - {c.reason}" if c.reason else ""
                    lines.append(f"  - {c.value}{reason}")
            lines.append("")

        # Logo规范
        if rules.logo:
            lines.append("### Logo规范")
            lines.append(f"- **位置**: {rules.logo.position_description}")
            if rules.logo.size_range:
                lines.append(f"- **尺寸范围**: {rules.logo.size_range.get('min', 5)}% - {rules.logo.size_range.get('max', 15)}%")
            lines.append(f"- **安全间距**: {rules.logo.safe_margin_px}px")
            lines.append("")

        # 字体规范
        if rules.font:
            lines.append("### 字体规范")
            if rules.font.allowed:
                lines.append(f"- **允许字体**: {', '.join(rules.font.allowed)}")
            if rules.font.forbidden:
                lines.append(f"- **禁用字体**: {', '.join(rules.font.forbidden)}")
            lines.append("")

        # 次要规范
        if hasattr(rules, 'secondary_rules') and rules.secondary_rules:
            lines.append("## 次要规范")
            lines.append("")
            categories = {}
            for rule in rules.secondary_rules:
                if rule.category not in categories:
                    categories[rule.category] = []
                categories[rule.category].append(rule)

            for category, rules_list in categories.items():
                lines.append(f"### {category}")
                for rule in sorted(rules_list, key=lambda x: x.priority):
                    lines.append(f"- **{rule.name}**: {rule.content}")
                lines.append("")

        return "\n".join(lines)

    def _upload_document(self):
        """上传规范文档"""
        file_paths, _ = QFileDialog.getOpenFileNames(
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

        if not file_paths:
            return

        # 从第一个文件名提取默认品牌名
        file_name = Path(file_paths[0]).stem
        default_name = file_name[:20] if len(file_name) > 20 else file_name

        # 弹出输入对话框让用户命名
        brand_name, ok = QInputDialog.getText(
            self, "品牌命名",
            f"已选择 {len(file_paths)} 个文件，请输入品牌名称:",
            QLineEdit.EchoMode.Normal,
            default_name
        )

        if not ok:
            return

        brand_name = brand_name.strip() if brand_name.strip() else default_name

        # 发送任务开始信号
        self.task_started.emit("规范文档解析")
        self.progress_updated.emit(-1, "正在解析文档...", f"开始解析 {len(file_paths)} 个文件")

        # 禁用按钮，显示处理中
        self.upload_btn.setEnabled(False)
        self.upload_btn.setText("解析中...")
        self._current_brand_name = brand_name
        self._current_files = file_paths

        # 后台线程解析
        if len(file_paths) == 1:
            # 单文件直接解析
            self._parse_worker = Worker(self._parse_with_progress, file_paths[0], brand_name)
        else:
            # 多文件合并解析
            self._parse_worker = Worker(self._parse_multiple_files, file_paths, brand_name)
        self._parse_worker.finished_signal.connect(self._on_parse_finished)
        self._parse_worker.error_signal.connect(self._on_parse_error)
        self._parse_worker.progress_signal.connect(lambda p, m: self.progress_updated.emit(p, m, m))
        self._parse_worker.start()

    def _parse_multiple_files(self, file_paths: list, brand_name: str, progress_callback=None):
        """解析多个文件并合并"""
        all_texts = []
        total = len(file_paths)

        for i, file_path in enumerate(file_paths):
            progress = int((i / total) * 80)
            self.progress_updated.emit(progress, f"解析文件 {i+1}/{total}...", f"正在解析: {Path(file_path).name}")

            rules = document_parser.parse_file(file_path, brand_name)
            if rules.raw_text:
                all_texts.append(f"=== 文件: {Path(file_path).name} ===\n{rules.raw_text}")

        # 合并所有文本
        combined_text = "\n\n".join(all_texts)
        self.progress_updated.emit(80, "正在合并去重...", "调用LLM合并规范")

        # 使用LLM合并去重
        merged_rules = self._merge_rules_with_llm(combined_text, brand_name)

        return merged_rules

    def _merge_rules_with_llm(self, combined_text: str, brand_name: str):
        """使用LLM合并多个文件的规范"""
        # 如果文本太长，截取
        max_chars = 20000
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars]

        # 使用document_parser的方法解析
        rules = document_parser._extract_rules_with_llm(combined_text, f"{brand_name}_合并")
        rules.brand_name = brand_name
        rules.raw_text = combined_text[:50000]  # 保留合并后的原文

        return rules

    def _parse_with_progress(self, file_path: str, brand_name: str, progress_callback=None):
        """带进度回调的文档解析"""
        self.progress_updated.emit(20, "正在提取文档内容...", "")
        result = document_parser.parse_file(file_path, brand_name)
        self.progress_updated.emit(80, "正在解析规范结构...", "")
        return result

    def _on_parse_finished(self, rules):
        """解析完成"""
        self.upload_btn.setEnabled(True)
        self.upload_btn.setText("上传规范文档")

        if hasattr(self, '_current_brand_name') and self._current_brand_name:
            rules.brand_name = self._current_brand_name

        brand_id = rules_context.add_rules(rules)

        self.task_finished.emit(True, f"规范文档解析完成: {rules.brand_name}")

        InfoBar.success(
            title="解析成功",
            content=f"品牌: {rules.brand_name}\nID: {brand_id}",
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self
        )

        self._load_rules_list()

    def _on_parse_error(self, error_msg):
        """解析失败"""
        self.upload_btn.setEnabled(True)
        self.upload_btn.setText("上传规范文档")

        self.task_finished.emit(False, f"解析失败: {error_msg}")

        InfoBar.error(
            title="解析失败",
            content=error_msg,
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

        brand_name = self.rules_combo.currentText()

        box = MessageBox(
            "确认删除",
            f"确定要删除规范 '{brand_name}' 吗？\n此操作不可恢复！",
            self
        )
        box.yesButton.setText("删除")
        box.cancelButton.setText("取消")

        if box.exec():
            rules_context.delete_rules(brand_id)
            self._load_rules_list()

            InfoBar.success(
                title="删除成功",
                content=f"已删除: {brand_name}",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )