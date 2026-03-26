"""审核页面 - 单图/批量审核（Fluent风格）"""

import json
import logging
from pathlib import Path
from datetime import datetime
import uuid
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog
from PySide6.QtGui import QColor, QPixmap

from qfluentwidgets import (
    ScrollArea, StrongBodyLabel, CaptionLabel, BodyLabel,
    PushButton, PrimaryPushButton, ComboBox, SpinBox,
    ProgressBar, TextEdit, TableWidget,
    InfoBar, InfoBarPosition, MessageBox, CardWidget,
    HeaderCardWidget, TabWidget, FluentIcon as FIF,
    SubtitleLabel, TitleLabel
)
from PySide6.QtWidgets import QTableWidgetItem

from gui.widgets import ImageDropArea
from gui.utils import Worker
from src.services.audit_service import audit_service
from src.services.rules_context import rules_context
from src.utils.config import get_app_dir

logger = logging.getLogger(__name__)


class AuditPage(ScrollArea):
    """审核页面 - Fluent风格"""

    # 进度信号: (percent, message, log_message)
    progress_updated = Signal(int, str, str)
    task_started = Signal(str)  # 任务名称
    task_finished = Signal(bool, str)  # 成功/失败, 消息
    # 流式结果信号: (result, index, completed, total)
    streaming_result = Signal(dict, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("auditPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.audit_result = None
        self._init_ui()

    def showEvent(self, event):
        """页面显示时自动刷新品牌列表"""
        super().showEvent(event)
        self._load_brand_list()
        self._load_batch_brand_list()

    def _init_ui(self):
        # 主容器
        self.view = QWidget()
        self.setWidget(self.view)

        layout = QVBoxLayout(self.view)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(20)

        # 标题
        title = TitleLabel("设计稿审核")
        layout.addWidget(title)

        # 提示信息
        hint = CaptionLabel("对设计稿进行完整的品牌合规审核，支持单图和批量审核")
        layout.addWidget(hint)

        # 标签页
        self.tab_widget = TabWidget()

        # 单图审核标签
        single_tab = self._create_single_audit_tab()
        self.tab_widget.addTab(single_tab, "单图审核")

        # 批量审核标签
        batch_tab = self._create_batch_audit_tab()
        self.tab_widget.addTab(batch_tab, "批量审核")

        layout.addWidget(self.tab_widget)

    def _create_single_audit_tab(self) -> QWidget:
        """创建单图审核标签页"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        # 左侧：设置区域
        left_card = CardWidget()
        left_card.setMinimumWidth(380)
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(16)

        # 审核设置
        settings_label = StrongBodyLabel("审核设置")
        left_layout.addWidget(settings_label)

        # 品牌选择
        brand_layout = QHBoxLayout()
        brand_label = BodyLabel("品牌规范:")
        brand_label.setFixedWidth(80)
        self.brand_combo = ComboBox()
        self.brand_combo.setMinimumWidth(260)
        brand_layout.addWidget(brand_label)
        brand_layout.addWidget(self.brand_combo)
        brand_layout.addStretch()
        left_layout.addLayout(brand_layout)

        # 压缩预设选择
        compression_layout = QHBoxLayout()
        compression_label = BodyLabel("图片压缩:")
        compression_label.setFixedWidth(80)
        self.single_compression_combo = ComboBox()
        self.single_compression_combo.addItems([
            "均衡（推荐）",
            "高质量",
            "高压缩",
            "不压缩"
        ])
        self.single_compression_combo.setToolTip(
            "均衡：1920px/500KB/75%，适合大多数场景\n"
            "高质量：2560px/1MB/90%，保留更多细节\n"
            "高压缩：1280px/300KB/60%，最小传输量\n"
            "不压缩：原图传输，消耗更多Token"
        )
        self.single_compression_combo.setMinimumWidth(260)
        compression_layout.addWidget(compression_label)
        compression_layout.addWidget(self.single_compression_combo)
        compression_layout.addStretch()
        left_layout.addLayout(compression_layout)

        # 图片选择
        image_label = StrongBodyLabel("设计稿图片")
        left_layout.addWidget(image_label)

        self.image_drop = ImageDropArea()
        self.image_drop.image_selected.connect(self._on_image_selected)
        left_layout.addWidget(self.image_drop)

        # 操作按钮
        self.audit_btn = PrimaryPushButton("开始审核")
        self.audit_btn.clicked.connect(self._on_audit)
        self.audit_btn.setEnabled(False)
        self.audit_btn.setMinimumHeight(45)
        left_layout.addWidget(self.audit_btn)

        # 进度
        self.progress_bar = ProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.status_label = CaptionLabel("")
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)

        left_layout.addStretch()
        layout.addWidget(left_card, 1)

        # 右侧：结果展示
        right_card = CardWidget()
        right_card.setMinimumWidth(520)
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)

        # 结果标题
        result_title = StrongBodyLabel("审核结果")
        right_layout.addWidget(result_title)

        # 评分区域
        score_card = CardWidget()
        score_card.setBorderRadius(8)
        score_layout = QHBoxLayout(score_card)
        score_layout.setContentsMargins(20, 20, 20, 20)

        self.score_label = TitleLabel("--")
        self.score_label.setStyleSheet("font-size: 32px;")
        score_layout.addWidget(self.score_label)

        score_layout.addStretch()

        self.status_badge = BodyLabel("")
        self.status_badge.setStyleSheet("padding: 8px 16px; border-radius: 12px; font-weight: bold;")
        score_layout.addWidget(self.status_badge)

        right_layout.addWidget(score_card)

        # 问题数量
        self.issue_count_label = CaptionLabel("问题数: --")
        right_layout.addWidget(self.issue_count_label)

        # 摘要
        self.summary_label = BodyLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setVisible(False)
        right_layout.addWidget(self.summary_label)

        # 检测结果标题
        self.detection_title = StrongBodyLabel("检测结果")
        self.detection_title.setVisible(False)
        right_layout.addWidget(self.detection_title)

        # 检测结果内容
        self.detection_content = BodyLabel("")
        self.detection_content.setWordWrap(True)
        self.detection_content.setVisible(False)
        right_layout.addWidget(self.detection_content)

        # 问题列表标题
        self.issues_title = StrongBodyLabel("问题列表")
        self.issues_title.setVisible(False)
        right_layout.addWidget(self.issues_title)

        # 问题表格
        self.issues_table = TableWidget()
        self.issues_table.setColumnCount(4)
        self.issues_table.setHorizontalHeaderLabels(["类型", "严重程度", "描述", "建议"])
        self.issues_table.horizontalHeader().setStretchLastSection(True)
        self.issues_table.setVisible(False)
        right_layout.addWidget(self.issues_table)

        right_layout.addStretch()

        # 提示信息
        hint_label = CaptionLabel("上方显示简化结果，完整报告请点击导出")
        right_layout.addWidget(hint_label)

        # 导出按钮
        export_layout = QHBoxLayout()
        self.export_json_btn = PushButton("导出JSON")
        self.export_json_btn.clicked.connect(lambda: self._on_export("json"))
        self.export_json_btn.setEnabled(False)

        self.export_md_btn = PushButton("导出Markdown")
        self.export_md_btn.clicked.connect(lambda: self._on_export("md"))
        self.export_md_btn.setEnabled(False)

        export_layout.addStretch()
        export_layout.addWidget(self.export_json_btn)
        export_layout.addWidget(self.export_md_btn)
        right_layout.addLayout(export_layout)

        layout.addWidget(right_card, 1)

        # 加载品牌列表
        self._load_brand_list()

        return widget

    def _create_batch_audit_tab(self) -> QWidget:
        """创建批量审核标签页"""
        widget = QWidget()

        # 外层滚动区域
        batch_scroll = ScrollArea()
        batch_scroll.setWidgetResizable(True)
        batch_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(16)

        # 提示卡片
        hint_card = CardWidget()
        hint_card.setBorderRadius(8)
        hint_layout = QVBoxLayout(hint_card)
        hint_layout.setContentsMargins(20, 16, 20, 16)
        hint_label = BodyLabel(
            "批量审核方案说明：\n"
            "• 并发请求：同时发送多个独立API请求，速度快但每张图都需传输规范Prompt\n"
            "• 合并请求：单次API调用处理多张图片，节省Prompt Token，响应解析更复杂\n"
            "• 图片压缩可显著减少Token消耗和传输时间"
        )
        hint_layout.addWidget(hint_label)
        layout.addWidget(hint_card)

        # 设置卡片
        settings_card = CardWidget()
        settings_card.setBorderRadius(8)
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        settings_layout.setSpacing(12)

        settings_title = StrongBodyLabel("批量审核设置")
        settings_layout.addWidget(settings_title)

        # 品牌选择
        brand_row = QHBoxLayout()
        brand_label = BodyLabel("品牌规范:")
        brand_label.setFixedWidth(80)
        self.batch_brand_combo = ComboBox()
        self.batch_brand_combo.setMinimumWidth(320)
        brand_row.addWidget(brand_label)
        brand_row.addWidget(self.batch_brand_combo)
        brand_row.addStretch()
        settings_layout.addLayout(brand_row)

        # 审核方案选择
        mode_row = QHBoxLayout()
        mode_label = BodyLabel("审核方案:")
        mode_label.setFixedWidth(80)
        self.audit_mode_combo = ComboBox()
        self.audit_mode_combo.addItems([
            "并发请求（推荐，速度快）",
            "合并请求（省Token，复杂）"
        ])
        self.audit_mode_combo.setToolTip(
            "并发请求：同时发送多个API请求，速度更快\n"
            "合并请求：单次API处理多图，节省Prompt重复传输"
        )
        self.audit_mode_combo.setMinimumWidth(320)
        mode_row.addWidget(mode_label)
        mode_row.addWidget(self.audit_mode_combo)
        mode_row.addStretch()
        settings_layout.addLayout(mode_row)

        # 并发数设置
        concurrent_row = QHBoxLayout()
        concurrent_label = BodyLabel("并发数:")
        concurrent_label.setFixedWidth(80)
        self.concurrent_spin = SpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(5)
        concurrent_row.addWidget(concurrent_label)
        concurrent_row.addWidget(self.concurrent_spin)
        concurrent_hint = CaptionLabel("(并发请求模式有效)")
        concurrent_row.addWidget(concurrent_hint)
        concurrent_row.addStretch()
        settings_layout.addLayout(concurrent_row)

        # 压缩预设选择
        compression_row = QHBoxLayout()
        compression_label = BodyLabel("图片压缩:")
        compression_label.setFixedWidth(80)
        self.compression_combo = ComboBox()
        self.compression_combo.addItems([
            "均衡（推荐，1920px/500KB/75%）",
            "高质量（2560px/1MB/90%）",
            "高压缩（1280px/300KB/60%）",
            "不压缩（原图传输）"
        ])
        self.compression_combo.setToolTip(
            "均衡：适合大多数场景，压缩效果和画质平衡\n"
            "高质量：保留更多细节，适合高清图片审核\n"
            "高压缩：最小传输量，适合网速较慢或大量图片\n"
            "不压缩：保留原图，消耗更多Token"
        )
        self.compression_combo.setMinimumWidth(320)
        compression_row.addWidget(compression_label)
        compression_row.addWidget(self.compression_combo)
        compression_row.addStretch()
        settings_layout.addLayout(compression_row)

        layout.addWidget(settings_card)

        # 图片上传卡片
        upload_card = CardWidget()
        upload_card.setBorderRadius(8)
        upload_layout = QVBoxLayout(upload_card)
        upload_layout.setContentsMargins(20, 20, 20, 20)
        upload_layout.setSpacing(12)

        upload_title = StrongBodyLabel("图片上传")
        upload_layout.addWidget(upload_title)

        # 多图选择
        self.multi_image_drop = ImageDropArea(multi_select=True, max_images=100)
        self.multi_image_drop.images_selected.connect(self._on_multi_images_selected)
        upload_layout.addWidget(self.multi_image_drop)

        # 文件计数
        self.file_count_label = CaptionLabel("已选择 0 张图片")
        upload_layout.addWidget(self.file_count_label)

        layout.addWidget(upload_card)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.batch_audit_btn = PrimaryPushButton("开始批量审核")
        self.batch_audit_btn.clicked.connect(self._on_batch_audit)
        self.batch_audit_btn.setEnabled(False)
        self.batch_audit_btn.setMinimumHeight(45)
        btn_layout.addWidget(self.batch_audit_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 进度显示
        self.batch_progress_bar = ProgressBar()
        self.batch_progress_bar.setVisible(False)
        layout.addWidget(self.batch_progress_bar)

        self.batch_status_label = CaptionLabel("")
        layout.addWidget(self.batch_status_label)

        # 批量结果卡片
        self.batch_result_card = CardWidget()
        self.batch_result_card.setVisible(False)
        self.batch_result_card.setBorderRadius(8)
        batch_result_layout = QVBoxLayout(self.batch_result_card)
        batch_result_layout.setContentsMargins(20, 20, 20, 20)
        batch_result_layout.setSpacing(12)

        batch_result_title = StrongBodyLabel("审核结果")
        batch_result_layout.addWidget(batch_result_title)

        self.batch_summary_label = BodyLabel("")
        batch_result_layout.addWidget(self.batch_summary_label)

        self.batch_result_list = TextEdit()
        self.batch_result_list.setReadOnly(True)
        self.batch_result_list.setMaximumHeight(200)
        batch_result_layout.addWidget(self.batch_result_list)

        # 提示信息
        batch_hint = CaptionLabel("上方显示简化结果，完整报告请点击导出")
        batch_result_layout.addWidget(batch_hint)

        # 批量导出按钮
        batch_export_layout = QHBoxLayout()
        self.batch_export_json_btn = PushButton("导出JSON")
        self.batch_export_json_btn.clicked.connect(lambda: self._on_batch_export("json"))
        self.batch_export_md_btn = PushButton("导出Markdown")
        self.batch_export_md_btn.clicked.connect(lambda: self._on_batch_export("md"))
        batch_export_layout.addStretch()
        batch_export_layout.addWidget(self.batch_export_json_btn)
        batch_export_layout.addWidget(self.batch_export_md_btn)
        batch_result_layout.addLayout(batch_export_layout)

        layout.addWidget(self.batch_result_card)
        layout.addStretch()

        batch_scroll.setWidget(scroll_content)

        # 主布局
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(batch_scroll)

        # 加载品牌列表
        self._load_batch_brand_list()

        return widget

    def _load_brand_list(self):
        """加载品牌列表"""
        self.brand_combo.clear()
        self.brand_combo.addItem("默认规范", None)

        rules_list = rules_context.list_rules()
        for rule in rules_list:
            brand_id = rule.get("brand_id", "")
            brand_name = rule.get("brand_name", "未命名")
            self.brand_combo.addItem(f"{brand_name}", brand_id)

    def _load_batch_brand_list(self):
        """加载批量审核品牌列表"""
        self.batch_brand_combo.clear()
        self.batch_brand_combo.addItem("默认规范", None)

        rules_list = rules_context.list_rules()
        for rule in rules_list:
            brand_id = rule.get("brand_id", "")
            brand_name = rule.get("brand_name", "未命名")
            self.batch_brand_combo.addItem(f"{brand_name}", brand_id)

    def _on_image_selected(self, image_path: str):
        self.audit_btn.setEnabled(bool(image_path))

    def _on_multi_images_selected(self, image_paths: list):
        self.file_count_label.setText(f"已选择 {len(image_paths)} 张图片")
        self.batch_audit_btn.setEnabled(len(image_paths) > 0)

    def _on_audit(self):
        """开始审核"""
        image_path = self.image_drop.get_first_image()
        if not image_path:
            return

        brand_id = self.brand_combo.currentData()

        # 获取用户选择的压缩预设
        compression_preset = ["balanced", "high_quality", "high_compression", "no_compression"][self.single_compression_combo.currentIndex()]
        audit_service.set_compression_preset(compression_preset)
        logger.info(f"单图审核使用压缩预设: {compression_preset}")

        # 发送任务开始信号
        self.task_started.emit("单图审核")
        self.progress_updated.emit(-1, "正在预处理图片...", f"开始审核: {Path(image_path).name}")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在审核（可能需要1-2分钟）...")
        self.audit_btn.setEnabled(False)

        # 后台任务
        self.worker = Worker(self._run_audit, image_path, brand_id)
        self.worker.finished_signal.connect(self._on_audit_finished)
        self.worker.error_signal.connect(self._on_audit_error)
        self.worker.progress_signal.connect(lambda p, m: self.progress_updated.emit(-1, m, m))
        self.worker.start()

    def _run_audit(self, image_path: str, brand_id: str, progress_callback=None):
        """执行审核"""
        self.progress_updated.emit(-1, "正在调用AI分析...", "图片预处理完成")
        result = audit_service.audit_file(image_path, brand_id)
        self.progress_updated.emit(80, "正在生成报告...", "AI分析完成")
        return result

    def _on_audit_finished(self, report):
        """审核完成"""
        self.audit_result = report

        self.progress_bar.setVisible(False)
        self.status_label.setText("审核完成!")
        self.audit_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)
        self.export_md_btn.setEnabled(True)

        # 发送任务完成信号
        grade_map = {'pass': '优', 'warning': '良', 'fail': '差'}
        status_map = {'pass': '通过', 'warning': '警告', 'fail': '不通过'}
        grade = grade_map.get(report.status.value, '未知')
        status = status_map.get(report.status.value, '未知')
        self.task_finished.emit(True, f"审核完成，结果: {grade} ({status})")

        # 保存到历史
        self._save_to_history(report)

        self._display_result(report)

    def _on_audit_error(self, error: str):
        """审核出错"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"审核失败: {error}")
        self.audit_btn.setEnabled(True)

        # 发送任务失败信号
        self.task_finished.emit(False, f"审核失败: {error}")

        InfoBar.error(
            title="错误",
            content=f"审核失败:\n{error}",
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _display_result(self, report):
        """显示审核结果"""
        # 根据状态显示等级
        grade_styles = {
            'pass': ('优', '#27ae60', '通过'),
            'warning': ('良', '#f39c12', '警告'),
            'fail': ('差', '#e74c3c', '不通过')
        }
        grade_text, color, status_text = grade_styles.get(report.status.value, ('--', '#95a5a6', '未知'))

        # 显示等级而非分数
        self.score_label.setText(grade_text)
        self.score_label.setStyleSheet(f"font-size: 32px; color: {color}; font-weight: bold;")

        # 状态徽章
        self.status_badge.setText(status_text)
        self.status_badge.setStyleSheet(f"""
            background-color: {color};
            color: white;
            padding: 8px 16px;
            border-radius: 12px;
            font-weight: bold;
        """)

        # 问题数量
        issues = report.issues
        critical = len([i for i in issues if i.severity.value == "critical"])
        major = len([i for i in issues if i.severity.value == "major"])
        minor = len([i for i in issues if i.severity.value == "minor"])
        self.issue_count_label.setText(f"问题数: {len(issues)}个 (严重:{critical} 主要:{major} 次要:{minor})")

        # 摘要
        if report.summary:
            self.summary_label.setText(f"总体评价: {report.summary}")
            self.summary_label.setVisible(True)
        else:
            self.summary_label.setVisible(False)

        # 检测结果
        detection = report.detection
        detection_parts = []

        # 颜色检测
        if detection.colors:
            colors_text = " ".join([f"{c.hex} {c.name} ({c.percent:.1f}%)" for c in detection.colors[:5]])
            detection_parts.append(f"颜色: {colors_text}")

        # Logo检测
        if detection.logo:
            logo_text = f"Logo: {'已检测到' if detection.logo.found else '未检测到'}"
            if detection.logo.found:
                logo_text += f" | 位置: {detection.logo.position or '未知'} | 尺寸: {detection.logo.size_percent or 0:.1f}%"
            detection_parts.append(logo_text)

        # 文字检测
        if detection.texts:
            texts_preview = "、".join(detection.texts[:5])
            if len(detection.texts) > 5:
                texts_preview += f" 等{len(detection.texts)}条"
            detection_parts.append(f"文字: {texts_preview}")

        # 字体检测
        if detection.fonts:
            fonts_text = "、".join([f.font_family for f in detection.fonts[:3] if f.font_family])
            if fonts_text:
                detection_parts.append(f"字体: {fonts_text}")

        if detection_parts:
            self.detection_content.setText("\n".join(detection_parts))
            self.detection_content.setVisible(True)
            self.detection_title.setVisible(True)
        else:
            self.detection_content.setVisible(False)
            self.detection_title.setVisible(False)

        # 问题列表
        if issues:
            self.issues_table.setRowCount(len(issues))
            self.issues_table.setVisible(True)
            self.issues_title.setVisible(True)

            severity_map = {
                'critical': '严重',
                'major': '主要',
                'minor': '次要'
            }

            severity_colors = {
                'critical': '#e74c3c',
                'major': '#f39c12',
                'minor': '#3498db'
            }

            for row, issue in enumerate(issues):
                self.issues_table.setItem(row, 0, QTableWidgetItem(issue.type.value.upper()))

                severity_text = severity_map.get(issue.severity.value, issue.severity.value)
                severity_item = QTableWidgetItem(severity_text)
                severity_item.setForeground(QColor(severity_colors.get(issue.severity.value, '#95a5a6')))
                self.issues_table.setItem(row, 1, severity_item)

                self.issues_table.setItem(row, 2, QTableWidgetItem(issue.description))
                self.issues_table.setItem(row, 3, QTableWidgetItem(issue.suggestion))
        else:
            self.issues_table.setVisible(False)
            self.issues_title.setVisible(False)

    def _save_to_history(self, report):
        """保存审核结果到历史"""
        history_dir = get_app_dir() / "data" / "audit_history"
        history_dir.mkdir(parents=True, exist_ok=True)

        batch_id = f"single_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        history_data = {
            "batch_id": batch_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brand_name": self.brand_combo.currentText(),
            "file_name": Path(self.image_drop.get_first_image()).name if self.image_drop.get_first_image() else "",
            "file_count": 1,
            "status": report.status.value,
            "score": report.score,
            "report": json.loads(report.to_json())
        }

        # 保存报告文件
        report_file = history_dir / f"{batch_id}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        # 更新历史索引
        index_file = history_dir / "history_index.json"
        history_list = []
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                history_list = json.load(f)

        history_list.insert(0, {
            "batch_id": batch_id,
            "time": history_data["time"],
            "brand_name": history_data["brand_name"],
            "file_name": history_data["file_name"],
            "file_count": 1,
            "status": history_data["status"],
            "score": history_data["score"],
        })

        # 只保留最近100条
        history_list = history_list[:100]

        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(history_list, f, ensure_ascii=False, indent=2)

    def _on_export(self, format_type: str):
        """导出报告"""
        if not self.audit_result:
            return

        export_dir = get_app_dir() / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format_type == "json":
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出JSON报告",
                str(export_dir / f"audit_report_{timestamp}.json"),
                "JSON文件 (*.json)"
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.audit_result.to_json())
                InfoBar.success(
                    title="成功",
                    content=f"已导出到:\n{file_path}",
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

        else:  # markdown
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出Markdown报告",
                str(export_dir / f"audit_report_{timestamp}.md"),
                "Markdown文件 (*.md)"
            )
            if file_path:
                md_content = self._report_to_markdown(self.audit_result)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                InfoBar.success(
                    title="成功",
                    content=f"已导出到:\n{file_path}",
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

    def _report_to_markdown(self, report) -> str:
        """将报告转换为Markdown - 完整版"""
        status_map = {"pass": "通过", "warning": "需修改", "fail": "不通过"}
        grade_map = {"pass": "优", "warning": "良", "fail": "差"}
        grade = grade_map.get(report.status.value, "未知")

        lines = [
            "# 品牌合规审核报告",
            "",
            f"**评级**: {grade}",
            f"**状态**: {status_map.get(report.status.value, report.status.value)}",
            "",
        ]

        # 摘要
        if report.summary:
            lines.extend([
                "## 总体评价",
                "",
                report.summary,
                "",
            ])

        # 检测结果
        lines.append("## 检测结果")
        lines.append("")

        detection = report.detection

        # Logo检测结果
        lines.append("### Logo检测")
        lines.append("")
        if detection.logo.found:
            lines.append(f"- **检测到Logo**: 是")
            lines.append(f"- **位置**: {detection.logo.position or '未知'}")
            if detection.logo.size_percent:
                lines.append(f"- **尺寸占比**: {detection.logo.size_percent:.1f}%")
            if detection.logo.position_correct is not None:
                pos_status = "正确" if detection.logo.position_correct else "错误"
                lines.append(f"- **位置正确**: {pos_status}")
            if detection.logo.color_correct is not None:
                color_status = "正确" if detection.logo.color_correct else "错误"
                lines.append(f"- **颜色正确**: {color_status}")
        else:
            lines.append("- **检测到Logo**: 否")
        lines.append("")

        # 颜色检测结果
        if detection.colors:
            lines.append("### 颜色检测")
            lines.append("")
            lines.append("| 颜色值 | 名称 | 占比 |")
            lines.append("|--------|------|------|")
            for c in detection.colors:
                lines.append(f"| {c.hex} | {c.name} | {c.percent:.1f}% |")
            lines.append("")

        # 文字检测结果
        if detection.texts:
            lines.append("### 文字检测 (OCR)")
            lines.append("")
            for i, text in enumerate(detection.texts[:10], 1):
                lines.append(f"{i}. {text}")
            if len(detection.texts) > 10:
                lines.append(f"_... 共 {len(detection.texts)} 条_")
            lines.append("")

        # 字体检测结果
        if detection.fonts:
            lines.append("### 字体检测")
            lines.append("")
            for f in detection.fonts:
                status = "禁用" if f.is_forbidden else "正常"
                lines.append(f"- **{f.text}**: {f.font_family} ({status})")
            lines.append("")

        # 检查项详情
        if report.checks:
            lines.append("## 检查项详情")
            lines.append("")

            check_titles = {
                "logo_checks": "Logo检查",
                "color_checks": "色彩检查",
                "font_checks": "字体检查",
                "layout_checks": "排版检查",
                "style_checks": "风格检查"
            }

            status_icons = {"pass": "", "warn": "", "fail": ""}

            for check_type, items in report.checks.items():
                if items:
                    lines.append(f"### {check_titles.get(check_type, check_type)}")
                    lines.append("")
                    for item in items:
                        icon = status_icons.get(item.status, "?")
                        lines.append(f"- {icon} **{item.code}** {item.name}: {item.detail}")
                    lines.append("")

        # 问题列表
        if report.issues:
            lines.append("## 问题列表")
            lines.append("")

            # 按严重程度分组
            critical = [i for i in report.issues if i.severity.value == "critical"]
            major = [i for i in report.issues if i.severity.value == "major"]
            minor = [i for i in report.issues if i.severity.value == "minor"]

            if critical:
                lines.append("### 严重问题")
                lines.append("")
                for issue in critical:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 建议: {issue.suggestion}")
                lines.append("")

            if major:
                lines.append("### 主要问题")
                lines.append("")
                for issue in major:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 建议: {issue.suggestion}")
                lines.append("")

            if minor:
                lines.append("### 次要问题")
                lines.append("")
                for issue in minor:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 建议: {issue.suggestion}")
                lines.append("")

        return "\n".join(lines)

    def _on_batch_audit(self):
        """批量审核"""
        image_paths = self.multi_image_drop.get_image_paths()
        if not image_paths:
            return

        brand_id = self.batch_brand_combo.currentData()

        # 获取用户选择的设置
        audit_mode = self.audit_mode_combo.currentIndex()  # 0=并发, 1=合并
        concurrent_count = self.concurrent_spin.value()
        compression_preset = ["balanced", "high_quality", "high_compression", "no_compression"][self.compression_combo.currentIndex()]

        # 设置压缩预设
        audit_service.set_compression_preset(compression_preset)
        logger.info(f"使用压缩预设: {compression_preset}")

        # 保存设置供_run_batch_audit使用
        self._audit_mode = audit_mode
        self._concurrent_count = concurrent_count
        self._total_images = len(image_paths)

        # 发送任务开始信号
        mode_text = "并发请求" if audit_mode == 0 else "合并请求"
        self.task_started.emit(f"批量审核 ({mode_text}模式)")
        self.progress_updated.emit(0, f"准备审核 {len(image_paths)} 张图片...", f"开始批量审核，共 {len(image_paths)} 张图片")

        self.batch_progress_bar.setVisible(True)
        self.batch_progress_bar.setRange(0, len(image_paths))
        self.batch_progress_bar.setValue(0)

        self.batch_status_label.setText(f"正在审核（{mode_text}模式）...")
        self.batch_audit_btn.setEnabled(False)
        self.batch_result_card.setVisible(True)  # 提前显示结果区域
        self.batch_result_list.clear()  # 清空之前的结果

        # 连接流式结果信号
        self.streaming_result.connect(self._on_streaming_result)

        # 后台任务
        self._batch_worker = Worker(self._run_batch_audit, image_paths, brand_id, audit_mode, concurrent_count)
        self._batch_worker.finished_signal.connect(self._on_batch_finished)
        self._batch_worker.error_signal.connect(self._on_batch_error)
        self._batch_worker.progress_signal.connect(self._on_batch_progress)
        self._batch_worker.start()

    def _on_streaming_result(self, result: dict, index: int, completed: int, total: int):
        """处理流式结果 - 实时更新UI"""
        status_icons = {"pass": "", "warning": "", "fail": "", "error": ""}
        status_icon = status_icons.get(result.get("status"), "?")
        grade_map = {"pass": "优", "warning": "良", "fail": "差", "error": "错误"}
        grade = grade_map.get(result.get("status"), "?")
        line = f"{status_icon} {result.get('file_name')} - 评级: {grade}"

        # 追加到结果列表
        current_text = self.batch_result_list.toPlainText()
        if current_text:
            self.batch_result_list.setPlainText(current_text + "\n" + line)
        else:
            self.batch_result_list.setPlainText(line)

        # 更新进度
        self.batch_progress_bar.setValue(completed)

    def _run_batch_audit(self, image_paths: list, brand_id: str, audit_mode: int = 0, concurrent_count: int = 5, progress_callback=None):
        """执行批量审核 - 根据用户选择调用不同方案"""
        import time

        mode_text = "并发请求" if audit_mode == 0 else "合并请求"
        logger.info(f"开始批量审核（{mode_text}模式），共 {len(image_paths)} 张图片")

        total = len(image_paths)
        self._streaming_results = []  # 存储流式结果

        def progress_cb(completed, total, message):
            """进度回调包装"""
            if progress_callback:
                progress_callback(completed, message)
            percent = int(completed / total * 100) if total > 0 else 0
            self.progress_updated.emit(percent, message, message)

        def result_cb(result, index, completed, total):
            """流式结果回调 - 每处理完一张图片就返回"""
            # 转换格式
            if result.get("status") == "success":
                report = result["report"]
                formatted = {
                    "file_name": result["file_name"],
                    "status": report.status.value,
                    "score": report.score,
                    "report": json.loads(report.to_json())
                }
            else:
                formatted = {
                    "file_name": result["file_name"],
                    "status": "error",
                    "error": result.get("error", "未知错误")
                }

            self._streaming_results.append(formatted)
            # 发送流式结果信号
            self.streaming_result.emit(formatted, index, completed, total)

        start_time = time.time()

        if audit_mode == 0:
            # 方案A: 并发请求
            audit_service.batch_audit_concurrent(
                image_paths=image_paths,
                brand_id=brand_id,
                max_concurrent=concurrent_count,
                progress_callback=progress_cb,
                result_callback=result_cb,
            )
        else:
            # 方案B: 合并请求
            audit_service.batch_audit_merged(
                image_paths=image_paths,
                brand_id=brand_id,
                max_images_per_request=None,  # 自动计算
                progress_callback=progress_cb,
                result_callback=result_cb,
            )

        elapsed = time.time() - start_time
        logger.info(f"批量审核完成，耗时: {elapsed:.1f}秒，平均每张: {elapsed/len(image_paths):.1f}秒")

        return self._streaming_results

    def _on_batch_progress(self, current: int, message: str):
        """批量审核进度"""
        self.batch_progress_bar.setValue(current)
        self.batch_status_label.setText(message)
        if hasattr(self, '_total_images') and self._total_images > 0:
            percent = int(current / self._total_images * 100)
            self.progress_updated.emit(percent, message, message)

    def _on_batch_finished(self, results: list):
        """批量审核完成"""
        # 断开流式结果信号
        try:
            self.streaming_result.disconnect(self._on_streaming_result)
        except:
            pass

        self.batch_progress_bar.setVisible(False)
        self.batch_audit_btn.setEnabled(True)

        # 计算摘要
        total = len(results)
        pass_count = len([r for r in results if r.get("status") == "pass"])
        warning_count = len([r for r in results if r.get("status") == "warning"])
        fail_count = len([r for r in results if r.get("status") == "fail"])
        error_count = len([r for r in results if r.get("status") == "error"])

        self.batch_summary_label.setText(
            f"总数: {total} | 优: {pass_count} | 良: {warning_count} | 差: {fail_count} | 错误: {error_count}"
        )

        self.batch_status_label.setText("批量审核完成!")

        # 发送任务完成信号
        self.task_finished.emit(True, f"批量审核完成，共 {total} 张，通过 {pass_count} 张")

        # 保存批量结果
        self._last_batch_results = results

        # 保存到历史
        self._save_batch_to_history(results)

    def _on_batch_error(self, error: str):
        """批量审核失败"""
        self.batch_progress_bar.setVisible(False)
        self.batch_audit_btn.setEnabled(True)
        self.batch_status_label.setText(f"批量审核失败: {error}")

        # 发送任务失败信号
        self.task_finished.emit(False, f"批量审核失败: {error}")

        InfoBar.error(
            title="错误",
            content=f"批量审核失败:\n{error}",
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=self
        )

    def _save_batch_to_history(self, results: list):
        """保存批量审核结果到历史"""
        history_dir = get_app_dir() / "data" / "audit_history"
        history_dir.mkdir(parents=True, exist_ok=True)

        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        pass_count = len([r for r in results if r.get("status") == "pass"])
        warning_count = len([r for r in results if r.get("status") == "warning"])
        fail_count = len([r for r in results if r.get("status") == "fail"])

        history_data = {
            "batch_id": batch_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brand_name": self.batch_brand_combo.currentText(),
            "file_count": len(results),
            "status": "completed",
            "summary": {
                "total": len(results),
                "pass_count": pass_count,
                "warning_count": warning_count,
                "fail_count": fail_count
            },
            "results": results
        }

        report_file = history_dir / f"{batch_id}.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        # 更新历史索引
        index_file = history_dir / "history_index.json"
        history_list = []
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                history_list = json.load(f)

        history_list.insert(0, {
            "batch_id": batch_id,
            "time": history_data["time"],
            "brand_name": history_data["brand_name"],
            "file_count": len(results),
            "status": "completed",
            "grade": "优" if pass_count > fail_count + warning_count else ("良" if warning_count >= fail_count else "差"),
        })

        history_list = history_list[:100]

        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(history_list, f, ensure_ascii=False, indent=2)

    def _on_batch_export(self, format_type: str):
        """导出批量报告"""
        if not hasattr(self, '_last_batch_results') or not self._last_batch_results:
            return

        export_dir = get_app_dir() / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format_type == "json":
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出批量JSON报告",
                str(export_dir / f"batch_report_{timestamp}.json"),
                "JSON文件 (*.json)"
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump({
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "results": self._last_batch_results
                    }, f, ensure_ascii=False, indent=2)
                InfoBar.success(
                    title="成功",
                    content=f"已导出到:\n{file_path}",
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
        elif format_type == "md":
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出批量Markdown报告",
                str(export_dir / f"batch_report_{timestamp}.md"),
                "Markdown文件 (*.md)"
            )
            if file_path:
                md_content = self._generate_batch_markdown()
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                InfoBar.success(
                    title="成功",
                    content=f"已导出到:\n{file_path}",
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

    def _generate_batch_markdown(self) -> str:
        """生成批量报告Markdown内容"""
        lines = [
            "# 批量审核报告",
            f"\n**生成时间:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n",
            "---\n"
        ]

        for i, result in enumerate(self._last_batch_results, 1):
            status_icon = {"pass": "", "warning": "", "fail": "", "error": ""}.get(result.get("status"), "?")
            grade_map = {"pass": "优", "warning": "良", "fail": "差", "error": "错误"}
            grade = grade_map.get(result.get("status"), "?")
            lines.append(f"## {i}. {result.get('file_name', '未知文件')}")
            lines.append(f"\n**状态:** {status_icon} {result.get('status', '-')}")
            lines.append(f"**评级:** {grade}\n")

            report = result.get("report", {})
            if report:
                if report.get("summary"):
                    lines.append("### 总体评价\n")
                    lines.append(report["summary"])
                    lines.append("")

                # 检测结果
                detection = report.get("detection", {})
                if detection:
                    lines.append("### 检测结果\n")
                    logo = detection.get("logo", {})
                    if logo:
                        lines.append(f"- **Logo:** {'已检测' if logo.get('found') else '未检测到'}")
                        if logo.get("found"):
                            lines.append(f"  - 位置: {logo.get('position', '-')}")
                            lines.append(f"  - 尺寸: {logo.get('size_percent', 0):.1f}%")
                    lines.append("")

                # 问题列表
                issues = report.get("issues", {})
                critical = issues.get("critical", [])
                major = issues.get("major", [])
                minor = issues.get("minor", [])

                if critical or major or minor:
                    lines.append("### 问题列表\n")
                    if critical:
                        lines.append("#### 严重问题")
                        for issue in critical:
                            lines.append(f"- {issue.get('description', '')}")
                            if issue.get("suggestion"):
                                lines.append(f"  - 建议: {issue['suggestion']}")
                        lines.append("")
                    if major:
                        lines.append("#### 主要问题")
                        for issue in major:
                            lines.append(f"- {issue.get('description', '')}")
                            if issue.get("suggestion"):
                                lines.append(f"  - 建议: {issue['suggestion']}")
                        lines.append("")
                    if minor:
                        lines.append("#### 次要问题")
                        for issue in minor:
                            lines.append(f"- {issue.get('description', '')}")
                            if issue.get("suggestion"):
                                lines.append(f"  - 建议: {issue['suggestion']}")
                        lines.append("")

            lines.append("---\n")

        return "\n".join(lines)