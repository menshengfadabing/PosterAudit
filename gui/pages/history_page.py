"""报告历史页面"""

import json
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QSplitter, QFrame, QTextEdit, QComboBox, QFileDialog,
    QScrollArea, QGridLayout
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
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)

        # 标题
        title = QLabel("审核历史")
        title.setStyleSheet("font-size: 26px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 说明
        desc = QLabel("查看和管理历史审核报告（历史记录持久化保存在 data/audit_history/ 目录）")
        desc.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        layout.addWidget(desc)

        # 主分割器
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # 左侧：报告列表
        left_panel = QFrame()
        left_panel.setStyleSheet("QFrame { background-color: white; border-radius: 8px; }")
        left_layout = QVBoxLayout(left_panel)

        # 筛选和刷新
        filter_layout = QHBoxLayout()
        filter_label = QLabel("筛选:")
        filter_label.setStyleSheet("font-size: 15px;")
        filter_layout.addWidget(filter_label)
        self.filter_combo = QComboBox()
        self.filter_combo.setStyleSheet("font-size: 15px; padding: 8px;")
        self.filter_combo.addItems(["全部", "通过", "需修改", "不通过"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setStyleSheet("font-size: 15px;")
        refresh_btn.clicked.connect(self.refresh)
        filter_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("清空历史")
        clear_btn.setStyleSheet("background-color: #e74c3c; color: white; font-size: 15px;")
        clear_btn.clicked.connect(self._on_clear_all)
        filter_layout.addWidget(clear_btn)
        left_layout.addLayout(filter_layout)

        # 报告表格
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["时间", "品牌", "文件数", "评分", "状态"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.history_table.setStyleSheet("font-size: 14px;")
        self.history_table.cellClicked.connect(self._on_row_clicked)
        left_layout.addWidget(self.history_table)

        # 统计
        self.stats_label = QLabel("共 0 条记录")
        self.stats_label.setStyleSheet("color: #7f8c8d; padding: 8px; font-size: 14px;")
        left_layout.addWidget(self.stats_label)

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

        self.open_folder_btn = QPushButton("打开目录")
        self.open_folder_btn.setStyleSheet("font-size: 15px;")
        self.open_folder_btn.clicked.connect(self._on_open_folder)

        export_layout.addStretch()
        export_layout.addWidget(self.export_json_btn)
        export_layout.addWidget(self.export_md_btn)
        export_layout.addWidget(self.open_folder_btn)
        left_layout.addLayout(export_layout)

        splitter.addWidget(left_panel)

        # 右侧：报告详情
        right_panel = QFrame()
        right_panel.setStyleSheet("QFrame { background-color: white; border-radius: 8px; }")
        right_layout = QVBoxLayout(right_panel)

        detail_title = QLabel("报告详情")
        detail_title.setStyleSheet("font-size: 18px; font-weight: bold;")
        right_layout.addWidget(detail_title)

        # 摘要区域
        self.summary_frame = QFrame()
        self.summary_frame.setStyleSheet("background-color: #f8f9fa; border-radius: 8px; padding: 15px;")
        self.summary_layout = QGridLayout(self.summary_frame)

        self.time_label = QLabel("--")
        self.brand_label = QLabel("--")
        self.score_label = QLabel("--")
        self.status_label = QLabel("--")

        time_lbl = QLabel("时间:")
        time_lbl.setStyleSheet("font-size: 15px;")
        brand_lbl = QLabel("品牌:")
        brand_lbl.setStyleSheet("font-size: 15px;")
        score_lbl = QLabel("评分:")
        score_lbl.setStyleSheet("font-size: 15px;")
        status_lbl = QLabel("状态:")
        status_lbl.setStyleSheet("font-size: 15px;")

        self.time_label.setStyleSheet("font-size: 15px;")
        self.brand_label.setStyleSheet("font-size: 15px;")
        self.score_label.setStyleSheet("font-size: 15px;")
        self.status_label.setStyleSheet("font-size: 15px;")

        self.summary_layout.addWidget(time_lbl, 0, 0)
        self.summary_layout.addWidget(self.time_label, 0, 1)
        self.summary_layout.addWidget(brand_lbl, 0, 2)
        self.summary_layout.addWidget(self.brand_label, 0, 3)
        self.summary_layout.addWidget(score_lbl, 1, 0)
        self.summary_layout.addWidget(self.score_label, 1, 1)
        self.summary_layout.addWidget(status_lbl, 1, 2)
        self.summary_layout.addWidget(self.status_label, 1, 3)

        right_layout.addWidget(self.summary_frame)

        # 详细内容
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("选择一条记录查看详情...")
        self.detail_text.setStyleSheet("border: 1px solid #ddd; border-radius: 5px; padding: 15px; font-size: 14px;")
        right_layout.addWidget(self.detail_text, 1)

        splitter.addWidget(right_panel)
        splitter.setSizes([500, 500])

        # 报告目录
        self.reports_dir = get_app_dir() / "data" / "audit_history"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.report_files = []
        self.refresh()

    def refresh(self):
        """刷新报告列表"""
        self.report_files = []
        self.history_table.setRowCount(0)

        # 读取历史索引
        index_file = self.reports_dir / "history_index.json"
        history_list = []
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    history_list = json.load(f)
            except Exception:
                pass

        # 如果索引为空，扫描所有文件
        if not history_list:
            json_files = list(self.reports_dir.glob("*.json"))
            json_files = [f for f in json_files if f.name != "history_index.json"]
            for file_path in sorted(json_files, key=lambda x: x.stat().st_mtime, reverse=True):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    history_list.append({
                        "batch_id": data.get("batch_id", file_path.stem),
                        "time": data.get("time", datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")),
                        "brand_name": data.get("brand_name", "-"),
                        "file_count": data.get("file_count", 1),
                        "status": data.get("status", data.get("report", {}).get("status", "unknown")),
                        "score": data.get("score", data.get("report", {}).get("score", 0)),
                    })
                except Exception:
                    continue

        filter_status = self.filter_combo.currentText()
        status_map = {"通过": "pass", "需修改": "warning", "不通过": "fail"}

        for item in history_list:
            status = item.get("status", "unknown")
            if filter_status != "全部":
                if status != status_map.get(filter_status, ""):
                    continue

            self.report_files.append({
                'batch_id': item.get("batch_id", ""),
                'time': item.get("time", "-"),
                'brand_name': item.get("brand_name", "-"),
                'file_count': item.get("file_count", 1),
                'score': item.get("score", 0),
                'status': status,
            })

        # 更新表格
        self.history_table.setRowCount(len(self.report_files))

        status_styles = {
            'pass': ('通过', '#27ae60'),
            'warning': ('需修改', '#f39c12'),
            'fail': ('不通过', '#e74c3c'),
            'completed': ('完成', '#27ae60'),
            'unknown': ('未知', '#95a5a6')
        }

        for row, file_info in enumerate(self.report_files):
            self.history_table.setItem(row, 0, QTableWidgetItem(file_info['time']))
            self.history_table.setItem(row, 1, QTableWidgetItem(file_info.get('brand_name', '-')))
            self.history_table.setItem(row, 2, QTableWidgetItem(str(file_info.get('file_count', 1))))

            score = file_info.get('score', 0)
            score_item = QTableWidgetItem(str(score) if score else "-")
            if score:
                if score >= 90:
                    score_item.setForeground(QColor('#27ae60'))
                elif score >= 70:
                    score_item.setForeground(QColor('#f39c12'))
                else:
                    score_item.setForeground(QColor('#e74c3c'))
            self.history_table.setItem(row, 3, score_item)

            status = file_info.get('status', 'unknown')
            status_text, status_color = status_styles.get(status, ('未知', '#95a5a6'))
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
            self.history_table.setItem(row, 4, status_item)

        self.stats_label.setText(f"共 {len(self.report_files)} 条记录")

    def _on_filter_changed(self):
        self.refresh()

    def _on_row_clicked(self, row: int, column: int):
        if row < len(self.report_files):
            self.export_json_btn.setEnabled(True)
            self.export_md_btn.setEnabled(True)
            file_info = self.report_files[row]
            self.current_report = file_info
            self._display_detail(file_info)

    def _display_detail(self, file_info: dict):
        """显示报告详情"""
        batch_id = file_info.get("batch_id", "")
        self.time_label.setText(file_info.get("time", "-"))
        self.brand_label.setText(file_info.get("brand_name", "-"))
        self.score_label.setText(str(file_info.get("score", "-")))
        self.status_label.setText(file_info.get("status", "-"))

        # 读取详细报告
        report_file = self.reports_dir / f"{batch_id}.json"
        if report_file.exists():
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._current_full_report = data
                self._render_report_detail(data)
            except Exception as e:
                self.detail_text.setText(f"读取报告失败: {e}")
        else:
            self.detail_text.setText("报告文件不存在")
            self._current_full_report = None

    def _render_report_detail(self, data: dict):
        """渲染报告详情"""
        lines = []

        # 判断是单图还是批量
        if "results" in data:
            # 批量审核
            summary = data.get("summary", {})
            lines.append("【批量审核摘要】")
            lines.append(f"总数: {summary.get('total', 0)}")
            lines.append(f"通过: {summary.get('pass_count', 0)}")
            lines.append(f"警告: {summary.get('warning_count', 0)}")
            lines.append(f"失败: {summary.get('fail_count', 0)}")
            lines.append(f"平均分: {summary.get('average_score', 0):.1f}")
            lines.append("")

            results = data.get("results", [])
            if results:
                lines.append(f"【详细结果 ({len(results)}项)】")
                for i, r in enumerate(results[:20]):  # 最多显示20条
                    status_icon = {"pass": "✅", "warning": "⚠️", "fail": "❌", "error": "🔴"}.get(r.get("status"), "❓")
                    lines.append(f"{status_icon} {r.get('file_name', '-')} - 分数: {r.get('score', 'N/A')}")

                if len(results) > 20:
                    lines.append(f"... 还有 {len(results) - 20} 条记录")

        elif "report" in data:
            # 单图审核
            report = data.get("report", {})
            lines.append("【审核摘要】")
            lines.append(report.get("summary", "-"))
            lines.append("")

            # 检测结果
            detection = report.get("detection", {})
            if detection:
                lines.append("【检测结果】")

                # Logo
                logo = detection.get("logo", {})
                if logo:
                    lines.append(f"Logo: {'已检测到' if logo.get('found') else '未检测到'}")
                    if logo.get("found"):
                        lines.append(f"  位置: {logo.get('position', '-')}")
                        lines.append(f"  尺寸: {logo.get('size_percent', 0):.1f}%")

                # 颜色
                colors = detection.get("colors", [])
                if colors:
                    lines.append(f"主要颜色:")
                    for c in colors[:5]:
                        lines.append(f"  {c.get('hex', '')} ({c.get('name', '')}) - {c.get('percent', 0):.1f}%")

                # 文字
                texts = detection.get("texts", [])
                if texts:
                    lines.append(f"检测到的文字: {', '.join(texts[:5])}{'...' if len(texts) > 5 else ''}")

                lines.append("")

            # 问题列表
            issues = report.get("issues", [])
            if issues:
                lines.append(f"【问题列表 ({len(issues)}项)】")
                for issue in issues[:15]:
                    severity = issue.get("severity", "minor").upper()
                    lines.append(f"[{severity}] {issue.get('description', '')}")
                    if issue.get("suggestion"):
                        lines.append(f"  💡 {issue.get('suggestion')}")

                if len(issues) > 15:
                    lines.append(f"... 还有 {len(issues) - 15} 个问题")

        self.detail_text.setText("\n".join(lines))

    def _on_export(self, format_type: str):
        """导出报告"""
        if not hasattr(self, '_current_full_report') or not self._current_full_report:
            QMessageBox.warning(self, "警告", "请先选择一条记录")
            return

        export_dir = get_app_dir() / "data" / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if format_type == "json":
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出JSON报告",
                str(export_dir / f"history_export_{timestamp}.json"),
                "JSON文件 (*.json)"
            )
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self._current_full_report, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")

        else:  # markdown
            file_path, _ = QFileDialog.getSaveFileName(
                self, "导出Markdown报告",
                str(export_dir / f"history_export_{timestamp}.md"),
                "Markdown文件 (*.md)"
            )
            if file_path:
                md_content = self._report_to_markdown(self._current_full_report)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                QMessageBox.information(self, "成功", f"已导出到:\n{file_path}")

    def _report_to_markdown(self, data: dict) -> str:
        """将报告转换为Markdown"""
        lines = [
            "# 审核历史报告",
            "",
            f"**时间**: {data.get('time', '-')}",
            f"**品牌**: {data.get('brand_name', '-')}",
            "",
        ]

        if "results" in data:
            # 批量报告
            summary = data.get("summary", {})
            lines.extend([
                "## 批量审核摘要",
                "",
                f"- 总数: {summary.get('total', 0)}",
                f"- 通过: {summary.get('pass_count', 0)}",
                f"- 警告: {summary.get('warning_count', 0)}",
                f"- 失败: {summary.get('fail_count', 0)}",
                f"- 平均分: {summary.get('average_score', 0):.1f}",
                "",
                "## 详细结果",
                "",
            ])

            for r in data.get("results", []):
                lines.append(f"- **{r.get('file_name', '-')}**: 分数 {r.get('score', 'N/A')}, 状态 {r.get('status', '-')}")

        elif "report" in data:
            # 单图报告
            report = data.get("report", {})
            lines.extend([
                f"**评分**: {report.get('score', 0)}/100",
                f"**状态**: {report.get('status', '-')}",
                f"**摘要**: {report.get('summary', '-')}",
                "",
                "## 问题列表",
                "",
            ])

            for issue in report.get("issues", []):
                lines.append(f"- **[{issue.get('severity', 'minor').upper()}]** {issue.get('description', '')}")
                if issue.get("suggestion"):
                    lines.append(f"  - 建议: {issue['suggestion']}")

        return "\n".join(lines)

    def _on_clear_all(self):
        """清空所有历史"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有历史记录吗？\n此操作不可恢复！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 删除所有JSON文件
            for f in self.reports_dir.glob("*.json"):
                f.unlink()

            self.refresh()
            self.detail_text.clear()
            self._current_full_report = None
            QMessageBox.information(self, "成功", "历史记录已清空")

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