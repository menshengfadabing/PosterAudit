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

    def showEvent(self, event):
        """页面显示时自动刷新"""
        super().showEvent(event)
        self.refresh()

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

        # 筛选和操作按钮
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

        # 删除选中按钮
        self.delete_btn = QPushButton("删除选中")
        self.delete_btn.setStyleSheet("background-color: #e74c3c; color: white; font-size: 15px;")
        self.delete_btn.clicked.connect(self._on_delete_selected)
        self.delete_btn.setEnabled(False)
        filter_layout.addWidget(self.delete_btn)

        clear_btn = QPushButton("清空历史")
        clear_btn.setStyleSheet("background-color: #c0392b; color: white; font-size: 15px;")
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

        export_layout.addStretch()
        export_layout.addWidget(self.export_json_btn)
        export_layout.addWidget(self.export_md_btn)
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

        # 提示信息
        hint_label = QLabel("💡 提示：上方显示的是简化版结果，查看完整报告请点击导出JSON或Markdown")
        hint_label.setStyleSheet("color: #7f8c8d; font-size: 12px; padding: 5px;")
        hint_label.setWordWrap(True)
        right_layout.addWidget(hint_label)

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
            self.delete_btn.setEnabled(True)  # 启用删除按钮
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
        """渲染报告详情 - 完整版"""
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
                lines.append("")

                for i, r in enumerate(results):  # 显示全部结果
                    status_icon = {"pass": "✅", "warning": "⚠️", "fail": "❌", "error": "🔴"}.get(r.get("status"), "❓")
                    lines.append(f"━━━ 图片 {i+1}: {r.get('file_name', '-')} ━━━")
                    lines.append(f"状态: {status_icon} | 分数: {r.get('score', 'N/A')}/100")
                    lines.append("")

                    report = r.get("report", {})
                    if report:
                        # 摘要
                        if report.get("summary"):
                            lines.append("📝 总体评价:")
                            lines.append(f"  {report['summary'][:200]}{'...' if len(report.get('summary', '')) > 200 else ''}")
                            lines.append("")

                        # 检测结果
                        detection = report.get("detection", {})
                        if detection:
                            # Logo
                            logo = detection.get("logo", {})
                            if logo:
                                if logo.get("found"):
                                    pos_ok = "✅" if logo.get("position_correct") else "❌"
                                    lines.append(f"🔍 Logo: 已检测 | 位置: {logo.get('position', '-')} ({pos_ok}) | 尺寸: {logo.get('size_percent', 0):.1f}%")
                                else:
                                    lines.append("🔍 Logo: 未检测到")
                                lines.append("")

                            # 颜色
                            colors = detection.get("colors", [])
                            if colors:
                                color_strs = [f"{c.get('hex', '')}({c.get('percent', 0):.0f}%)" for c in colors[:5]]
                                lines.append(f"🎨 颜色: {', '.join(color_strs)}")
                                lines.append("")

                            # 字体
                            fonts = detection.get("fonts", [])
                            if fonts:
                                forbidden = [f for f in fonts if f.get("is_forbidden")]
                                if forbidden:
                                    lines.append(f"🚫 禁用字体: {', '.join([f.get('text', '')[:15] for f in forbidden[:3]])}")
                                else:
                                    lines.append("✅ 字体: 无禁用字体")
                                lines.append("")

                        # 检查项摘要
                        checks = report.get("checks", {})
                        if checks:
                            fail_count = sum(1 for items in checks.values() for item in items if item.get("status") == "fail")
                            warn_count = sum(1 for items in checks.values() for item in items if item.get("status") == "warn")
                            pass_count = sum(1 for items in checks.values() for item in items if item.get("status") == "pass")
                            lines.append(f"📋 检查项: ✅{pass_count} ⚠️{warn_count} ❌{fail_count}")
                            lines.append("")

                        # 问题列表
                        issues = report.get("issues", [])
                        if issues:
                            critical = [i for i in issues if i.get("severity") == "critical"]
                            major = [i for i in issues if i.get("severity") == "major"]
                            minor = [i for i in issues if i.get("severity") == "minor"]
                            lines.append(f"⚠️ 问题: 🔴严重{len(critical)} 🟡主要{len(major)} 🟢次要{len(minor)}")

                    lines.append("")

        elif "report" in data:
            # 单图审核
            report = data.get("report", {})
            status_icon = {"pass": "✅", "warning": "⚠️", "fail": "❌"}.get(report.get("status"), "❓")
            lines.append(f"【审核结果】评分: {report.get('score', 0)}/100 | 状态: {status_icon}")
            lines.append("")

            # 摘要
            if report.get("summary"):
                lines.append("📝 总体评价:")
                lines.append(report["summary"])
                lines.append("")

            # 检测结果
            detection = report.get("detection", {})
            if detection:
                lines.append("【检测结果】")
                lines.append("")

                # Logo
                logo = detection.get("logo", {})
                if logo:
                    if logo.get("found"):
                        pos_ok = "✅正确" if logo.get("position_correct") else "❌错误"
                        lines.append(f"🔍 Logo: 已检测")
                        lines.append(f"   位置: {logo.get('position', '-')} ({pos_ok})")
                        if logo.get("size_percent"):
                            lines.append(f"   尺寸: {logo['size_percent']:.1f}%")
                    else:
                        lines.append("🔍 Logo: 未检测到")
                    lines.append("")

                # 颜色
                colors = detection.get("colors", [])
                if colors:
                    lines.append("🎨 主要颜色:")
                    for c in colors[:6]:
                        lines.append(f"   {c.get('hex', '')} {c.get('name', '')} - {c.get('percent', 0):.1f}%")
                    lines.append("")

                # 文字
                texts = detection.get("texts", [])
                if texts:
                    lines.append(f"📝 检测到的文字 ({len(texts)}条):")
                    for t in texts[:8]:
                        lines.append(f"   • {t[:50]}{'...' if len(t) > 50 else ''}")
                    if len(texts) > 8:
                        lines.append(f"   ... 还有 {len(texts) - 8} 条")
                    lines.append("")

                # 字体
                fonts = detection.get("fonts", [])
                if fonts:
                    lines.append("🔤 字体检测:")
                    for f in fonts[:5]:
                        status = "🚫禁用" if f.get("is_forbidden") else "✅正常"
                        lines.append(f"   • {f.get('text', '')[:20]}: {f.get('font_family', '-')} ({status})")
                    lines.append("")

            # 检查项
            checks = report.get("checks", {})
            if checks:
                lines.append("【检查项详情】")
                lines.append("")

                check_titles = {
                    "logo_checks": "Logo检查",
                    "color_checks": "色彩检查",
                    "font_checks": "字体检查",
                    "layout_checks": "排版检查",
                    "style_checks": "风格检查"
                }

                status_icons = {"pass": "✅", "warn": "⚠️", "fail": "❌"}

                for check_type, items in checks.items():
                    if items:
                        # 统计
                        fail_cnt = sum(1 for item in items if item.get("status") == "fail")
                        if fail_cnt > 0:
                            lines.append(f"📋 {check_titles.get(check_type, check_type)}:")
                            for item in items:
                                if item.get("status") == "fail":
                                    icon = status_icons.get(item.get("status"), "❓")
                                    lines.append(f"   {icon} {item.get('code', '')} {item.get('name', '')}")
                                    lines.append(f"      {item.get('detail', '')[:80]}")
                            lines.append("")

            # 问题列表
            issues = report.get("issues", [])
            if issues:
                lines.append(f"【问题列表 ({len(issues)}项)】")
                lines.append("")

                critical = [i for i in issues if i.get("severity") == "critical"]
                major = [i for i in issues if i.get("severity") == "major"]
                minor = [i for i in issues if i.get("severity") == "minor"]

                if critical:
                    lines.append("🔴 严重问题:")
                    for issue in critical:
                        lines.append(f"   • {issue.get('description', '')}")
                        if issue.get("suggestion"):
                            lines.append(f"     💡 {issue['suggestion'][:60]}")
                    lines.append("")

                if major:
                    lines.append("🟡 主要问题:")
                    for issue in major:
                        lines.append(f"   • {issue.get('description', '')}")
                        if issue.get("suggestion"):
                            lines.append(f"     💡 {issue['suggestion'][:60]}")
                    lines.append("")

                if minor:
                    lines.append("🟢 次要问题:")
                    for issue in minor[:5]:
                        lines.append(f"   • {issue.get('description', '')}")
                    if len(minor) > 5:
                        lines.append(f"   ... 还有 {len(minor) - 5} 个次要问题")

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
        """将报告转换为Markdown - 完整版"""
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
            ])

            # 详细结果 - 包含完整的每张图片报告
            for i, r in enumerate(data.get("results", []), 1):
                lines.append(f"## 图片 {i}: {r.get('file_name', '-')}")
                lines.append("")

                report = r.get("report", {})
                if report:
                    status_map = {"pass": "✅ 通过", "warning": "⚠️ 需修改", "fail": "❌ 不通过", "error": "🔴 错误"}
                    lines.append(f"**评分**: {report.get('score', 0)}/100")
                    lines.append(f"**状态**: {status_map.get(r.get('status'), r.get('status', '-'))}")
                    lines.append("")

                    # 摘要
                    if report.get("summary"):
                        lines.append("### 总体评价")
                        lines.append("")
                        lines.append(report["summary"])
                        lines.append("")

                    # 检测结果
                    detection = report.get("detection", {})
                    if detection:
                        lines.append("### 检测结果")
                        lines.append("")

                        # Logo
                        logo = detection.get("logo", {})
                        if logo:
                            lines.append("#### Logo检测")
                            lines.append("")
                            if logo.get("found"):
                                lines.append(f"- **检测到Logo**: 是")
                                lines.append(f"- **位置**: {logo.get('position', '未知')}")
                                if logo.get("size_percent"):
                                    lines.append(f"- **尺寸占比**: {logo['size_percent']:.1f}%")
                                if logo.get("position_correct") is not None:
                                    pos_status = "✅ 正确" if logo["position_correct"] else "❌ 错误"
                                    lines.append(f"- **位置正确**: {pos_status}")
                            else:
                                lines.append("- **检测到Logo**: 否")
                            lines.append("")

                        # 颜色
                        colors = detection.get("colors", [])
                        if colors:
                            lines.append("#### 颜色检测")
                            lines.append("")
                            lines.append("| 颜色值 | 名称 | 占比 |")
                            lines.append("|--------|------|------|")
                            for c in colors:
                                lines.append(f"| {c.get('hex', '')} | {c.get('name', '')} | {c.get('percent', 0):.1f}% |")
                            lines.append("")

                        # 文字
                        texts = detection.get("texts", [])
                        if texts:
                            lines.append("#### 文字检测 (OCR)")
                            lines.append("")
                            for j, text in enumerate(texts[:10], 1):
                                lines.append(f"{j}. {text}")
                            if len(texts) > 10:
                                lines.append(f"_... 共 {len(texts)} 条_")
                            lines.append("")

                        # 字体
                        fonts = detection.get("fonts", [])
                        if fonts:
                            lines.append("#### 字体检测")
                            lines.append("")
                            for f in fonts:
                                status = "🚫 禁用" if f.get("is_forbidden") else "✅ 正常"
                                lines.append(f"- **{f.get('text', '')}**: {f.get('font_family', '')} ({status})")
                            lines.append("")

                    # 检查项
                    checks = report.get("checks", {})
                    if checks:
                        lines.append("### 检查项详情")
                        lines.append("")

                        check_titles = {
                            "logo_checks": "Logo检查",
                            "color_checks": "色彩检查",
                            "font_checks": "字体检查",
                            "layout_checks": "排版检查",
                            "style_checks": "风格检查"
                        }

                        status_icons = {"pass": "✅", "warn": "⚠️", "fail": "❌"}

                        for check_type, items in checks.items():
                            if items:
                                lines.append(f"#### {check_titles.get(check_type, check_type)}")
                                lines.append("")
                                for item in items:
                                    icon = status_icons.get(item.get("status"), "❓")
                                    lines.append(f"- {icon} **{item.get('code', '')}** {item.get('name', '')}: {item.get('detail', '')}")
                                lines.append("")

                    # 问题列表
                    issues = report.get("issues", [])
                    if issues:
                        lines.append("### 问题列表")
                        lines.append("")

                        critical = [i for i in issues if i.get("severity") == "critical"]
                        major = [i for i in issues if i.get("severity") == "major"]
                        minor = [i for i in issues if i.get("severity") == "minor"]

                        if critical:
                            lines.append("#### 🔴 严重问题")
                            lines.append("")
                            for issue in critical:
                                lines.append(f"- {issue.get('description', '')}")
                                if issue.get("suggestion"):
                                    lines.append(f"  - 💡 建议: {issue['suggestion']}")
                            lines.append("")

                        if major:
                            lines.append("#### 🟡 主要问题")
                            lines.append("")
                            for issue in major:
                                lines.append(f"- {issue.get('description', '')}")
                                if issue.get("suggestion"):
                                    lines.append(f"  - 💡 建议: {issue['suggestion']}")
                            lines.append("")

                        if minor:
                            lines.append("#### 🟢 次要问题")
                            lines.append("")
                            for issue in minor:
                                lines.append(f"- {issue.get('description', '')}")
                                if issue.get("suggestion"):
                                    lines.append(f"  - 💡 建议: {issue['suggestion']}")
                            lines.append("")

                lines.append("---")
                lines.append("")

        elif "report" in data:
            # 单图报告
            report = data.get("report", {})
            status_map = {"pass": "✅ 通过", "warning": "⚠️ 需修改", "fail": "❌ 不通过"}
            lines.extend([
                f"**评分**: {report.get('score', 0)}/100",
                f"**状态**: {status_map.get(report.get('status'), report.get('status', '-'))}",
                "",
            ])

            # 摘要
            if report.get("summary"):
                lines.extend([
                    "## 总体评价",
                    "",
                    report["summary"],
                    "",
                ])

            # 检测结果
            detection = report.get("detection", {})
            if detection:
                lines.append("## 检测结果")
                lines.append("")

                # Logo
                logo = detection.get("logo", {})
                if logo:
                    lines.append("### Logo检测")
                    lines.append("")
                    if logo.get("found"):
                        lines.append(f"- **检测到Logo**: 是")
                        lines.append(f"- **位置**: {logo.get('position', '未知')}")
                        if logo.get("size_percent"):
                            lines.append(f"- **尺寸占比**: {logo['size_percent']:.1f}%")
                        if logo.get("position_correct") is not None:
                            pos_status = "✅ 正确" if logo["position_correct"] else "❌ 错误"
                            lines.append(f"- **位置正确**: {pos_status}")
                    else:
                        lines.append("- **检测到Logo**: 否")
                    lines.append("")

                # 颜色
                colors = detection.get("colors", [])
                if colors:
                    lines.append("### 颜色检测")
                    lines.append("")
                    lines.append("| 颜色值 | 名称 | 占比 |")
                    lines.append("|--------|------|------|")
                    for c in colors:
                        lines.append(f"| {c.get('hex', '')} | {c.get('name', '')} | {c.get('percent', 0):.1f}% |")
                    lines.append("")

                # 文字
                texts = detection.get("texts", [])
                if texts:
                    lines.append("### 文字检测 (OCR)")
                    lines.append("")
                    for j, text in enumerate(texts[:10], 1):
                        lines.append(f"{j}. {text}")
                    if len(texts) > 10:
                        lines.append(f"_... 共 {len(texts)} 条_")
                    lines.append("")

                # 字体
                fonts = detection.get("fonts", [])
                if fonts:
                    lines.append("### 字体检测")
                    lines.append("")
                    for f in fonts:
                        status = "🚫 禁用" if f.get("is_forbidden") else "✅ 正常"
                        lines.append(f"- **{f.get('text', '')}**: {f.get('font_family', '')} ({status})")
                    lines.append("")

            # 检查项
            checks = report.get("checks", {})
            if checks:
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

                for check_type, items in checks.items():
                    if items:
                        lines.append(f"### {check_titles.get(check_type, check_type)}")
                        lines.append("")
                        for item in items:
                            icon = status_icons.get(item.get("status"), "❓")
                            lines.append(f"- {icon} **{item.get('code', '')}** {item.get('name', '')}: {item.get('detail', '')}")
                        lines.append("")

            # 问题列表
            issues = report.get("issues", [])
            if issues:
                lines.append("## 问题列表")
                lines.append("")

                critical = [i for i in issues if i.get("severity") == "critical"]
                major = [i for i in issues if i.get("severity") == "major"]
                minor = [i for i in issues if i.get("severity") == "minor"]

                if critical:
                    lines.append("### 🔴 严重问题")
                    lines.append("")
                    for issue in critical:
                        lines.append(f"- {issue.get('description', '')}")
                        if issue.get("suggestion"):
                            lines.append(f"  - 💡 建议: {issue['suggestion']}")
                    lines.append("")

                if major:
                    lines.append("### 🟡 主要问题")
                    lines.append("")
                    for issue in major:
                        lines.append(f"- {issue.get('description', '')}")
                        if issue.get("suggestion"):
                            lines.append(f"  - 💡 建议: {issue['suggestion']}")
                    lines.append("")

                if minor:
                    lines.append("### 🟢 次要问题")
                    lines.append("")
                    for issue in minor:
                        lines.append(f"- {issue.get('description', '')}")
                        if issue.get("suggestion"):
                            lines.append(f"  - 💡 建议: {issue['suggestion']}")
                    lines.append("")

        return "\n".join(lines)

    def _on_delete_selected(self):
        """删除选中的记录"""
        if not self.current_report:
            QMessageBox.warning(self, "警告", "请先选择要删除的记录")
            return

        batch_id = self.current_report.get("batch_id", "")
        if not batch_id:
            QMessageBox.warning(self, "警告", "无法获取记录ID")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除这条记录吗？\n时间: {self.current_report.get('time', '-')}\n品牌: {self.current_report.get('brand_name', '-')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 删除JSON文件
            report_file = self.reports_dir / f"{batch_id}.json"
            if report_file.exists():
                report_file.unlink()

            # 更新索引文件
            index_file = self.reports_dir / "history_index.json"
            if index_file.exists():
                try:
                    with open(index_file, 'r', encoding='utf-8') as f:
                        history_list = json.load(f)
                    # 移除被删除的记录
                    history_list = [item for item in history_list if item.get("batch_id") != batch_id]
                    with open(index_file, 'w', encoding='utf-8') as f:
                        json.dump(history_list, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            # 清空当前选中状态
            self.current_report = None
            self._current_full_report = None
            self.history_table.clearSelection()
            self.detail_text.clear()
            self.delete_btn.setEnabled(False)
            self.export_json_btn.setEnabled(False)
            self.export_md_btn.setEnabled(False)

            # 刷新列表并更新统计
            self.refresh()
            QMessageBox.information(self, "成功", "记录已删除")

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

            # 清空索引文件
            index_file = self.reports_dir / "history_index.json"
            if index_file.exists():
                try:
                    with open(index_file, 'w', encoding='utf-8') as f:
                        json.dump([], f)
                except Exception:
                    pass

            self.refresh()
            self.detail_text.clear()
            self._current_full_report = None
            QMessageBox.information(self, "成功", "历史记录已清空")