"""审核页面 - 单图/批量审核"""

import json
from pathlib import Path
from datetime import datetime
import uuid
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QMessageBox, QSplitter, QFrame, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QTabWidget, QComboBox, QCheckBox, QFileDialog, QScrollArea,
    QGridLayout, QSpinBox, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap

from gui.widgets import ImageDropArea
from gui.utils import Worker
from src.services.audit_service import audit_service
from src.services.rules_context import rules_context
from src.utils.config import get_app_dir


class AuditPage(QWidget):
    """审核页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audit_result = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        # 标题
        title = QLabel("设计稿审核")
        title.setStyleSheet("font-size: 26px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 提示信息
        hint = QLabel("对设计稿进行完整的品牌合规审核，支持单图和批量审核")
        hint.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        layout.addWidget(hint)

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

        # 单图审核标签
        single_tab = self._create_single_audit_tab()
        tab_widget.addTab(single_tab, "单图审核")

        # 批量审核标签
        batch_tab = self._create_batch_audit_tab()
        tab_widget.addTab(batch_tab, "批量审核")

        layout.addWidget(tab_widget)

    def _create_single_audit_tab(self) -> QWidget:
        """创建单图审核标签页"""
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

        # 左侧：设置区域
        left_panel = QFrame()
        left_panel.setStyleSheet("QFrame { background-color: white; border-radius: 8px; }")
        left_panel.setMinimumWidth(350)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_layout.setSpacing(18)

        # 品牌选择
        brand_group = QGroupBox("审核设置")
        brand_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                padding-top: 15px;
            }
        """)
        brand_layout = QVBoxLayout(brand_group)

        brand_row = QHBoxLayout()
        brand_label = QLabel("品牌规范:")
        brand_label.setStyleSheet("font-size: 15px;")
        brand_row.addWidget(brand_label)
        self.brand_combo = QComboBox()
        self.brand_combo.setMinimumWidth(250)
        self.brand_combo.setStyleSheet("""
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
            QComboBox QAbstractItemView {
                background-color: white;
                color: #2c3e50;
                selection-background-color: #3498db;
                selection-color: white;
                font-size: 15px;
            }
        """)
        self._load_brand_list()
        brand_row.addWidget(self.brand_combo)
        brand_layout.addLayout(brand_row)

        # 刷新按钮
        refresh_row = QHBoxLayout()
        refresh_btn = QPushButton("刷新品牌列表")
        refresh_btn.setStyleSheet("font-size: 15px;")
        refresh_btn.clicked.connect(self._load_brand_list)
        refresh_row.addWidget(refresh_btn)
        refresh_row.addStretch()
        brand_layout.addLayout(refresh_row)

        left_layout.addWidget(brand_group)

        # 图片选择
        image_group = QGroupBox("设计稿图片")
        image_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                padding-top: 15px;
            }
        """)
        image_layout = QVBoxLayout(image_group)
        self.image_drop = ImageDropArea()
        self.image_drop.image_selected.connect(self._on_image_selected)
        image_layout.addWidget(self.image_drop)
        left_layout.addWidget(image_group)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.audit_btn = QPushButton("开始审核")
        self.audit_btn.clicked.connect(self._on_audit)
        self.audit_btn.setEnabled(False)
        self.audit_btn.setMinimumHeight(50)
        self.audit_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 15px 50px;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        btn_layout.addWidget(self.audit_btn)
        left_layout.addLayout(btn_layout)

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        self.status_label.setWordWrap(True)
        left_layout.addWidget(self.status_label)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # 右侧：结果展示
        right_panel = QFrame()
        right_panel.setStyleSheet("QFrame { background-color: white; border-radius: 8px; }")
        right_panel.setMinimumWidth(500)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(15, 15, 15, 15)

        # 结果标题
        result_title = QLabel("审核结果")
        result_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        right_layout.addWidget(result_title)

        # 评分区域
        score_frame = QFrame()
        score_frame.setStyleSheet("background-color: #ecf0f1; border-radius: 10px; padding: 20px;")
        score_layout = QGridLayout(score_frame)

        self.score_label = QLabel("--")
        self.score_label.setStyleSheet("font-size: 56px; font-weight: bold; color: #2c3e50;")
        score_layout.addWidget(self.score_label, 0, 0)

        self.score_suffix = QLabel("/100")
        self.score_suffix.setStyleSheet("font-size: 28px; color: #7f8c8d;")
        score_layout.addWidget(self.score_suffix, 0, 1)

        self.status_badge = QLabel("")
        self.status_badge.setStyleSheet("padding: 10px 20px; border-radius: 15px; font-weight: bold; font-size: 15px;")
        score_layout.addWidget(self.status_badge, 0, 2)

        self.issue_count_label = QLabel("问题数: --")
        self.issue_count_label.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        score_layout.addWidget(self.issue_count_label, 1, 0, 1, 3)

        right_layout.addWidget(score_frame)

        # 创建滚动区域显示详细结果
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self.result_widget = QWidget()
        self.result_layout = QVBoxLayout(self.result_widget)
        self.result_layout.setSpacing(12)

        # 摘要
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #34495e; padding: 15px; background-color: #f8f9fa; border-radius: 5px; font-size: 14px;")
        self.summary_label.setVisible(False)
        self.result_layout.addWidget(self.summary_label)

        # 检测结果标题
        detection_title = QLabel("检测结果")
        detection_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        detection_title.setVisible(False)
        self.result_layout.addWidget(detection_title)
        self.detection_title = detection_title

        # 检测结果内容
        self.detection_content = QLabel("")
        self.detection_content.setWordWrap(True)
        self.detection_content.setStyleSheet("padding: 15px; background-color: #f0f7ff; border-radius: 5px; font-size: 14px;")
        self.detection_content.setVisible(False)
        self.result_layout.addWidget(self.detection_content)

        # 问题列表
        issues_title = QLabel("问题列表")
        issues_title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        issues_title.setVisible(False)
        self.result_layout.addWidget(issues_title)
        self.issues_title = issues_title

        self.issues_table = QTableWidget()
        self.issues_table.setColumnCount(4)
        self.issues_table.setHorizontalHeaderLabels(["类型", "严重程度", "描述", "建议"])
        self.issues_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.issues_table.setStyleSheet("font-size: 14px;")
        self.issues_table.setVisible(False)
        self.result_layout.addWidget(self.issues_table)

        self.result_layout.addStretch()
        scroll.setWidget(self.result_widget)
        right_layout.addWidget(scroll, 1)

        # 导出按钮
        export_layout = QHBoxLayout()
        self.export_json_btn = QPushButton("导出JSON")
        self.export_json_btn.setStyleSheet("font-size: 15px;")
        self.export_json_btn.clicked.connect(lambda: self._on_export("json"))
        self.export_json_btn.setEnabled(False)

        self.export_md_btn = QPushButton("导出Markdown")
        self.export_md_btn.setStyleSheet("font-size: 15px;")
        self.export_md_btn.clicked.connect(lambda: self._on_export("md"))
        self.export_md_btn.setEnabled(False)

        export_layout.addStretch()
        export_layout.addWidget(self.export_json_btn)
        export_layout.addWidget(self.export_md_btn)
        right_layout.addLayout(export_layout)

        splitter.addWidget(right_panel)

        # 设置初始比例
        splitter.setSizes([400, 700])

        layout.addWidget(splitter)

        return widget

    def _create_batch_audit_tab(self) -> QWidget:
        """创建批量审核标签页"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(18)

        # 提示信息 - 更新为准确的时间预估
        hint_frame = QFrame()
        hint_frame.setStyleSheet("background-color: #FEF3C7; border-radius: 8px; padding: 15px;")
        hint_layout = QVBoxLayout(hint_frame)
        hint_label = QLabel(
            "批量审核预估时间：\n"
            "• 单张图片约需 45-90 秒\n"
            "• 10张图片约需 2-4 分钟（并发处理）\n"
            "• 图片会自动压缩以节省时间和Token消耗"
        )
        hint_label.setStyleSheet("color: #92400E; font-size: 14px;")
        hint_layout.addWidget(hint_label)
        layout.addWidget(hint_frame)

        # 设置区域
        settings_group = QGroupBox("批量审核设置")
        settings_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                padding-top: 15px;
            }
        """)
        settings_layout = QGridLayout(settings_group)

        # 品牌选择
        brand_label = QLabel("品牌规范:")
        brand_label.setStyleSheet("font-size: 15px;")
        settings_layout.addWidget(brand_label, 0, 0)
        self.batch_brand_combo = QComboBox()
        self.batch_brand_combo.setMinimumWidth(300)
        self.batch_brand_combo.setStyleSheet("""
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
            QComboBox QAbstractItemView {
                background-color: white;
                color: #2c3e50;
                selection-background-color: #3498db;
                selection-color: white;
                font-size: 15px;
            }
        """)
        self._load_batch_brand_list()
        settings_layout.addWidget(self.batch_brand_combo, 0, 1)

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet("font-size: 15px;")
        refresh_btn.clicked.connect(self._load_batch_brand_list)
        settings_layout.addWidget(refresh_btn, 0, 2)

        layout.addWidget(settings_group)

        # 图片上传区域
        upload_group = QGroupBox("图片上传")
        upload_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                padding-top: 15px;
            }
        """)
        upload_layout = QVBoxLayout(upload_group)

        # 多图选择
        self.multi_image_drop = ImageDropArea(multi_select=True, max_images=100)
        self.multi_image_drop.images_selected.connect(self._on_multi_images_selected)
        upload_layout.addWidget(self.multi_image_drop)

        # 文件计数
        self.file_count_label = QLabel("已选择 0 张图片")
        self.file_count_label.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        upload_layout.addWidget(self.file_count_label)

        layout.addWidget(upload_group)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.batch_audit_btn = QPushButton("开始批量审核")
        self.batch_audit_btn.clicked.connect(self._on_batch_audit)
        self.batch_audit_btn.setEnabled(False)
        self.batch_audit_btn.setMinimumHeight(50)
        self.batch_audit_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        btn_layout.addStretch()
        btn_layout.addWidget(self.batch_audit_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 进度显示
        self.batch_progress_bar = QProgressBar()
        self.batch_progress_bar.setVisible(False)
        layout.addWidget(self.batch_progress_bar)

        self.batch_status_label = QLabel("")
        self.batch_status_label.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        layout.addWidget(self.batch_status_label)

        # 批量结果预览（简化版）
        self.batch_result_group = QGroupBox("审核结果")
        self.batch_result_group.setVisible(False)
        self.batch_result_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                padding-top: 15px;
            }
        """)
        batch_result_layout = QVBoxLayout(self.batch_result_group)

        self.batch_summary_label = QLabel("")
        self.batch_summary_label.setStyleSheet("font-size: 15px;")
        batch_result_layout.addWidget(self.batch_summary_label)

        self.batch_result_list = QTextEdit()
        self.batch_result_list.setReadOnly(True)
        self.batch_result_list.setMaximumHeight(200)
        self.batch_result_list.setStyleSheet("font-size: 14px;")
        batch_result_layout.addWidget(self.batch_result_list)

        # 批量导出按钮
        batch_export_layout = QHBoxLayout()
        self.batch_export_json_btn = QPushButton("导出JSON")
        self.batch_export_json_btn.setStyleSheet("font-size: 15px;")
        self.batch_export_json_btn.clicked.connect(lambda: self._on_batch_export("json"))
        batch_export_layout.addStretch()
        batch_export_layout.addWidget(self.batch_export_json_btn)
        batch_result_layout.addLayout(batch_export_layout)

        layout.addWidget(self.batch_result_group)

        layout.addStretch()
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

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在审核（可能需要1-2分钟）...")
        self.audit_btn.setEnabled(False)

        # 后台任务
        self.worker = Worker(self._run_audit, image_path, brand_id)
        self.worker.finished_signal.connect(self._on_audit_finished)
        self.worker.error_signal.connect(self._on_audit_error)
        self.worker.start()

    def _run_audit(self, image_path: str, brand_id: str, progress_callback=None):
        """执行审核"""
        return audit_service.audit_file(image_path, brand_id)

    def _on_audit_finished(self, report):
        """审核完成"""
        self.audit_result = report

        self.progress_bar.setVisible(False)
        self.status_label.setText("审核完成!")
        self.audit_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)
        self.export_md_btn.setEnabled(True)

        # 保存到历史
        self._save_to_history(report)

        self._display_result(report)

    def _on_audit_error(self, error: str):
        """审核出错"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"审核失败: {error}")
        self.audit_btn.setEnabled(True)
        QMessageBox.critical(self, "错误", f"审核失败:\n{error}")

    def _display_result(self, report):
        """显示审核结果"""
        # 评分
        self.score_label.setText(str(report.score))

        # 状态徽章
        status_styles = {
            'pass': ('通过', '#27ae60'),
            'warning': ('需修改', '#f39c12'),
            'fail': ('不通过', '#e74c3c')
        }
        status_text, color = status_styles.get(report.status.value, ('未知', '#95a5a6'))
        self.status_badge.setText(status_text)
        self.status_badge.setStyleSheet(f"""
            background-color: {color};
            color: white;
            padding: 8px 16px;
            border-radius: 15px;
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
            self.summary_label.setText(f"📝 总体评价: {report.summary}")
            self.summary_label.setVisible(True)
        else:
            self.summary_label.setVisible(False)

        # 检测结果
        detection = report.detection
        detection_parts = []

        # 颜色检测
        if detection.colors:
            colors_text = " ".join([f"<span style='background-color:{c.hex};color:white;padding:2px 6px;border-radius:3px;'>{c.hex}</span> {c.name} ({c.percent:.1f}%)" for c in detection.colors[:5]])
            detection_parts.append(f"<b>颜色:</b> {colors_text}")

        # Logo检测
        if detection.logo:
            logo_text = f"<b>Logo:</b> {'已检测到' if detection.logo.found else '未检测到'}"
            if detection.logo.found:
                logo_text += f" | 位置: {detection.logo.position or '未知'} | 尺寸: {detection.logo.size_percent or 0:.1f}%"
            detection_parts.append(logo_text)

        # 文字检测
        if detection.texts:
            texts_preview = "、".join(detection.texts[:5])
            if len(detection.texts) > 5:
                texts_preview += f" 等{len(detection.texts)}条"
            detection_parts.append(f"<b>文字:</b> {texts_preview}")

        # 字体检测
        if detection.fonts:
            fonts_text = "、".join([f.font_family for f in detection.fonts[:3] if f.font_family])
            if fonts_text:
                detection_parts.append(f"<b>字体:</b> {fonts_text}")

        if detection_parts:
            self.detection_content.setText("<br>".join(detection_parts))
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
                QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")

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
                QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")

    def _report_to_markdown(self, report) -> str:
        """将报告转换为Markdown - 完整版"""
        status_map = {"pass": "✅ 通过", "warning": "⚠️ 需修改", "fail": "❌ 不通过"}

        lines = [
            "# 品牌合规审核报告",
            "",
            f"**评分**: {report.score}/100",
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
                pos_status = "✅ 正确" if detection.logo.position_correct else "❌ 错误"
                lines.append(f"- **位置正确**: {pos_status}")
            if detection.logo.color_correct is not None:
                color_status = "✅ 正确" if detection.logo.color_correct else "❌ 错误"
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
                status = "🚫 禁用" if f.is_forbidden else "✅ 正常"
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

            status_icons = {"pass": "✅", "warn": "⚠️", "fail": "❌"}

            for check_type, items in report.checks.items():
                if items:
                    lines.append(f"### {check_titles.get(check_type, check_type)}")
                    lines.append("")
                    for item in items:
                        icon = status_icons.get(item.status, "❓")
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
                lines.append("### 🔴 严重问题")
                lines.append("")
                for issue in critical:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 💡 建议: {issue.suggestion}")
                lines.append("")

            if major:
                lines.append("### 🟡 主要问题")
                lines.append("")
                for issue in major:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 💡 建议: {issue.suggestion}")
                lines.append("")

            if minor:
                lines.append("### 🟢 次要问题")
                lines.append("")
                for issue in minor:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 💡 建议: {issue.suggestion}")
                lines.append("")

        return "\n".join(lines)

    def _on_batch_audit(self):
        """批量审核"""
        image_paths = self.multi_image_drop.get_image_paths()
        if not image_paths:
            return

        brand_id = self.batch_brand_combo.currentData()

        self.batch_progress_bar.setVisible(True)
        self.batch_progress_bar.setRange(0, len(image_paths))
        self.batch_progress_bar.setValue(0)
        self.batch_status_label.setText("正在审核...")
        self.batch_audit_btn.setEnabled(False)
        self.batch_result_group.setVisible(False)

        # 后台任务
        self._batch_worker = Worker(self._run_batch_audit, image_paths, brand_id)
        self._batch_worker.finished_signal.connect(self._on_batch_finished)
        self._batch_worker.error_signal.connect(self._on_batch_error)
        self._batch_worker.progress_signal.connect(self._on_batch_progress)
        self._batch_worker.start()

    def _run_batch_audit(self, image_paths: list, brand_id: str, progress_callback=None):
        """执行批量审核 - 使用并发处理"""
        import concurrent.futures

        results = [None] * len(image_paths)
        total = len(image_paths)

        def audit_single(index, path):
            """审核单张图片"""
            try:
                report = audit_service.audit_file(path, brand_id)
                return index, {
                    "file_name": Path(path).name,
                    "status": report.status.value,
                    "score": report.score,
                    "report": json.loads(report.to_json())
                }
            except Exception as e:
                return index, {
                    "file_name": Path(path).name,
                    "status": "error",
                    "error": str(e)
                }

        # 并发审核，最大5个并发
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(audit_single, i, path): i
                for i, path in enumerate(image_paths)
            }

            for future in concurrent.futures.as_completed(futures):
                index, result = future.result()
                results[index] = result
                completed += 1

                if progress_callback:
                    progress_callback(completed, f"已完成 {completed}/{total}")

        return results

    def _on_batch_progress(self, current: int, message: str):
        """批量审核进度"""
        self.batch_progress_bar.setValue(current)
        self.batch_status_label.setText(message)

    def _on_batch_finished(self, results: list):
        """批量审核完成"""
        self.batch_progress_bar.setVisible(False)
        self.batch_audit_btn.setEnabled(True)
        self.batch_result_group.setVisible(True)

        # 计算摘要
        total = len(results)
        pass_count = len([r for r in results if r.get("status") == "pass"])
        warning_count = len([r for r in results if r.get("status") == "warning"])
        fail_count = len([r for r in results if r.get("status") == "fail"])
        error_count = len([r for r in results if r.get("status") == "error"])

        scores = [r.get("score", 0) for r in results if r.get("score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0

        self.batch_summary_label.setText(
            f"总数: {total} | 通过: {pass_count} | 警告: {warning_count} | 失败: {fail_count} | 错误: {error_count} | 平均分: {avg_score:.1f}"
        )

        # 结果列表
        result_lines = []
        for r in results:
            status_icon = {"pass": "✅", "warning": "⚠️", "fail": "❌", "error": "🔴"}.get(r.get("status"), "❓")
            result_lines.append(f"{status_icon} {r.get('file_name')} - 分数: {r.get('score', 'N/A')}")

        self.batch_result_list.setText("\n".join(result_lines))
        self.batch_status_label.setText("批量审核完成!")

        # 保存批量结果
        self._last_batch_results = results

        # 保存到历史
        self._save_batch_to_history(results)

    def _on_batch_error(self, error: str):
        """批量审核失败"""
        self.batch_progress_bar.setVisible(False)
        self.batch_audit_btn.setEnabled(True)
        self.batch_status_label.setText(f"批量审核失败: {error}")
        QMessageBox.critical(self, "错误", f"批量审核失败:\n{error}")

    def _save_batch_to_history(self, results: list):
        """保存批量审核结果到历史"""
        history_dir = get_app_dir() / "data" / "audit_history"
        history_dir.mkdir(parents=True, exist_ok=True)

        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        pass_count = len([r for r in results if r.get("status") == "pass"])
        warning_count = len([r for r in results if r.get("status") == "warning"])
        fail_count = len([r for r in results if r.get("status") == "fail"])

        scores = [r.get("score", 0) for r in results if r.get("score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0

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
                "fail_count": fail_count,
                "average_score": round(avg_score, 1)
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
            "score": round(avg_score, 1),
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
                QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")