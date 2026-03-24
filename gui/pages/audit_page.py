"""审核页面 - 单图审核"""

import json
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QMessageBox, QSplitter, QFrame, QTextEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from gui.widgets import ImageDropArea
from gui.utils import Worker
from src.services.audit_service import audit_service
from src.services.rules_context import rules_context


class AuditPage(QWidget):
    """审核页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.audit_result = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 标题
        title = QLabel("设计稿审核")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 说明
        desc = QLabel("对设计稿进行完整的品牌合规审核")
        desc.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(desc)

        # 主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # 左侧：设置区域
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)

        # 图片选择
        image_group = QGroupBox("设计稿图片")
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
        self.audit_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 12px 40px;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #219a52;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
        """)
        btn_layout.addStretch()
        btn_layout.addWidget(self.audit_btn)
        btn_layout.addStretch()
        left_layout.addLayout(btn_layout)

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #7f8c8d;")
        left_layout.addWidget(self.status_label)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # 右侧：结果展示
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)

        # 结果标题
        result_title = QLabel("审核结果")
        result_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(result_title)

        # 评分区域
        score_frame = QFrame()
        score_frame.setStyleSheet("background-color: #ecf0f1; border-radius: 10px; padding: 15px;")
        score_layout = QVBoxLayout(score_frame)

        score_row = QHBoxLayout()
        self.score_label = QLabel("--")
        self.score_label.setStyleSheet("font-size: 48px; font-weight: bold; color: #2c3e50;")
        score_row.addWidget(self.score_label)

        self.score_suffix = QLabel("/100")
        self.score_suffix.setStyleSheet("font-size: 24px; color: #7f8c8d;")
        score_row.addWidget(self.score_suffix)
        score_row.addStretch()

        self.status_badge = QLabel("")
        self.status_badge.setStyleSheet("padding: 8px 16px; border-radius: 15px; font-weight: bold;")
        score_row.addWidget(self.status_badge)

        score_layout.addLayout(score_row)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #34495e; margin-top: 10px;")
        score_layout.addWidget(self.summary_label)

        right_layout.addWidget(score_frame)

        # 问题列表
        issues_group = QGroupBox("问题列表")
        issues_layout = QVBoxLayout(issues_group)
        self.issues_table = QTableWidget()
        self.issues_table.setColumnCount(4)
        self.issues_table.setHorizontalHeaderLabels(["类型", "严重程度", "描述", "建议"])
        self.issues_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        issues_layout.addWidget(self.issues_table)
        right_layout.addWidget(issues_group, 1)

        # 导出按钮
        export_layout = QHBoxLayout()
        self.export_json_btn = QPushButton("导出JSON")
        self.export_json_btn.clicked.connect(lambda: self._on_export("json"))
        self.export_json_btn.setEnabled(False)

        self.export_md_btn = QPushButton("导出Markdown")
        self.export_md_btn.clicked.connect(lambda: self._on_export("md"))
        self.export_md_btn.setEnabled(False)

        export_layout.addStretch()
        export_layout.addWidget(self.export_json_btn)
        export_layout.addWidget(self.export_md_btn)
        right_layout.addLayout(export_layout)

        splitter.addWidget(right_panel)
        splitter.setSizes([400, 600])

    def _on_image_selected(self, image_path: str):
        self.audit_btn.setEnabled(bool(image_path))

    def _on_audit(self):
        """开始审核"""
        image_path = self.image_drop.get_first_image()
        if not image_path:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("正在审核...")
        self.audit_btn.setEnabled(False)

        # 后台任务
        self.worker = Worker(self._run_audit, image_path)
        self.worker.finished_signal.connect(self._on_audit_finished)
        self.worker.error_signal.connect(self._on_audit_error)
        self.worker.start()

    def _run_audit(self, image_path: str, progress_callback=None):
        """执行审核"""
        return audit_service.audit_file(image_path)

    def _on_audit_finished(self, report):
        """审核完成"""
        self.audit_result = report

        self.progress_bar.setVisible(False)
        self.status_label.setText("审核完成!")
        self.audit_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)
        self.export_md_btn.setEnabled(True)

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

        # 摘要
        self.summary_label.setText(report.summary)

        # 问题列表
        issues = report.issues
        self.issues_table.setRowCount(len(issues))

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
            # 类型
            self.issues_table.setItem(row, 0, QTableWidgetItem(issue.type.value.upper()))

            # 严重程度
            severity_text = severity_map.get(issue.severity.value, issue.severity.value)
            severity_item = QTableWidgetItem(severity_text)
            severity_item.setForeground(QColor(severity_colors.get(issue.severity.value, '#95a5a6')))
            self.issues_table.setItem(row, 1, severity_item)

            # 描述
            self.issues_table.setItem(row, 2, QTableWidgetItem(issue.description))

            # 建议
            self.issues_table.setItem(row, 3, QTableWidgetItem(issue.suggestion))

    def _on_export(self, format_type: str):
        """导出报告"""
        if not self.audit_result:
            return

        if format_type == "json":
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出JSON报告",
                f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                "JSON文件 (*.json)"
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.audit_result.to_json())
                QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")

        else:  # markdown
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出Markdown报告",
                f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                "Markdown文件 (*.md)"
            )
            if file_path:
                md_content = self._report_to_markdown(self.audit_result)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")

    def _report_to_markdown(self, report) -> str:
        """将报告转换为Markdown"""
        lines = [
            "# 品牌合规审核报告",
            "",
            f"**评分**: {report.score}/100",
            f"**状态**: {report.status.value}",
            f"**摘要**: {report.summary}",
            "",
            "## 检测结果",
            "",
            "### Logo",
            f"- 检测到Logo: {'是' if report.detection.logo.found else '否'}",
        ]

        if report.detection.logo.found:
            lines.extend([
                f"- 位置: {report.detection.logo.position}",
                f"- 尺寸占比: {report.detection.logo.size_percent}%",
            ])

        lines.extend([
            "",
            "### 颜色",
        ])

        for color in report.detection.colors:
            lines.append(f"- {color.hex} ({color.name}): {color.percent:.1f}%")

        if report.issues:
            lines.extend([
                "",
                "## 问题列表",
                "",
            ])

            for issue in report.issues:
                lines.append(f"- **[{issue.severity.value}]** {issue.description}")
                if issue.suggestion:
                    lines.append(f"  - 建议: {issue.suggestion}")

        return "\n".join(lines)