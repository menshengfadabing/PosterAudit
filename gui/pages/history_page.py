"""报告历史页面"""

import json
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSplitter, QFrame, QTextEdit, QComboBox, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.utils.config import get_app_dir


class HistoryPage(QWidget):
    """报告历史页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_report = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # 标题
        title = QLabel("报告历史")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 说明
        desc = QLabel("查看和管理历史审核报告")
        desc.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(desc)

        # 主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # 左侧：报告列表
        left_panel = QFrame()
        left_layout = QVBoxLayout(left_panel)

        # 筛选
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "通过", "需修改", "不通过"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(refresh_btn)
        left_layout.addLayout(filter_layout)

        # 报告表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["时间", "评分", "状态", "文件名"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.cellClicked.connect(self._on_row_clicked)
        left_layout.addWidget(self.history_table)

        # 统计
        self.stats_label = QLabel("共 0 条记录")
        left_layout.addWidget(self.stats_label)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self._on_delete)
        self.delete_btn.setEnabled(False)

        self.open_folder_btn = QPushButton("打开目录")
        self.open_folder_btn.clicked.connect(self._on_open_folder)

        btn_layout.addStretch()
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.open_folder_btn)
        left_layout.addLayout(btn_layout)

        splitter.addWidget(left_panel)

        # 右侧：报告详情
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)

        detail_title = QLabel("报告详情")
        detail_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        right_layout.addWidget(detail_title)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        right_layout.addWidget(self.detail_text, 1)

        splitter.addWidget(right_panel)
        splitter.setSizes([600, 400])

        # 报告目录
        self.reports_dir = get_app_dir() / "data" / "audit_history"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.report_files = []
        self.refresh()

    def refresh(self):
        """刷新报告列表"""
        self.report_files = []
        self.history_table.setRowCount(0)

        json_files = list(self.reports_dir.glob("*.json"))
        all_files = sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True)

        filter_status = self.filter_combo.currentText()
        status_map = {"通过": "pass", "需修改": "warning", "不通过": "fail"}

        for file_path in all_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                file_info = {
                    'path': str(file_path),
                    'filename': file_path.name,
                    'time': datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
                    'score': data.get('score', 0),
                    'status': data.get('status', 'unknown'),
                    'data': data
                }

                if filter_status != "全部":
                    if file_info['status'] != status_map.get(filter_status, ""):
                        continue

                self.report_files.append(file_info)

            except Exception as e:
                print(f"Error reading {file_path}: {e}")
                continue

        # 更新表格
        self.history_table.setRowCount(len(self.report_files))

        status_styles = {
            'pass': ('通过', '#27ae60'),
            'warning': ('需修改', '#f39c12'),
            'fail': ('不通过', '#e74c3c'),
            'unknown': ('未知', '#95a5a6')
        }

        for row, file_info in enumerate(self.report_files):
            self.history_table.setItem(row, 0, QTableWidgetItem(file_info['time']))

            score = file_info['score']
            score_item = QTableWidgetItem(str(score))
            if score >= 90:
                score_item.setForeground(QColor('#27ae60'))
            elif score >= 70:
                score_item.setForeground(QColor('#f39c12'))
            else:
                score_item.setForeground(QColor('#e74c3c'))
            self.history_table.setItem(row, 1, score_item)

            status = file_info['status']
            status_text, status_color = status_styles.get(status, ('未知', '#95a5a6'))
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            self.history_table.setItem(row, 2, status_item)

            self.history_table.setItem(row, 3, QTableWidgetItem(file_info['filename']))

        self.stats_label.setText(f"共 {len(self.report_files)} 条记录")

    def _on_filter_changed(self):
        self.refresh()

    def _on_row_clicked(self, row: int, column: int):
        if row < len(self.report_files):
            self.delete_btn.setEnabled(True)
            file_info = self.report_files[row]
            self.current_report = file_info
            self._display_detail(file_info)

    def _display_detail(self, file_info: dict):
        """显示报告详情"""
        data = file_info.get('data', {})

        summary = f"""
=== 审核报告 ===

时间: {file_info.get('time', '-')}
评分: {data.get('score', '-')}
状态: {data.get('status', '-')}

=== 摘要 ===
{data.get('summary', '-')}

=== 问题 ({len(data.get('issues', []))} 项) ===
"""

        for issue in data.get('issues', [])[:10]:
            summary += f"\n• [{issue.get('severity', 'info').upper()}] {issue.get('description', '')}"
            if issue.get('suggestion'):
                summary += f"\n  建议: {issue.get('suggestion')}"

        self.detail_text.setText(summary)

    def _on_delete(self):
        """删除报告"""
        if not self.current_report:
            return

        path = self.current_report.get('path', '')

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除报告 '{self.current_report.get('filename', '')}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                Path(path).unlink()
                self.refresh()
                self.detail_text.clear()
                QMessageBox.information(self, "成功", "报告已删除")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除失败: {e}")

    def _on_open_folder(self):
        """打开报告目录"""
        import subprocess
        import sys

        if sys.platform == 'win32':
            subprocess.run(['explorer', str(self.reports_dir)])
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(self.reports_dir)])
        else:
            subprocess.run(['xdg-open', str(self.reports_dir)])