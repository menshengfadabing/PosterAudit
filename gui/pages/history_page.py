"""报告历史页面（Fluent风格）"""

import json
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog
from PySide6.QtGui import QColor

from qfluentwidgets import (
    ScrollArea, StrongBodyLabel, CaptionLabel, BodyLabel,
    PushButton, PrimaryPushButton, ComboBox, TextEdit,
    TableWidget, InfoBar, InfoBarPosition,
    MessageBox, CardWidget, TitleLabel, SubtitleLabel, FluentIcon as FIF
)
from PySide6.QtWidgets import QTableWidgetItem

from src.utils.config import get_app_dir
from gui.widgets.streaming_text_display import StreamingAuditDisplay


class HistoryPage(ScrollArea):
    """报告历史页面 - Fluent风格"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("historyPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.current_report = None
        self._init_ui()

    def showEvent(self, event):
        """页面显示时自动刷新"""
        super().showEvent(event)
        self.refresh()

    def _init_ui(self):
        # 主容器
        self.view = QWidget()
        self.setWidget(self.view)

        layout = QVBoxLayout(self.view)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(20)

        # 标题
        title = TitleLabel("审核历史")
        layout.addWidget(title)

        # 说明
        desc = CaptionLabel("查看和管理历史审核报告（历史记录持久化保存在 data/audit_history/ 目录）")
        layout.addWidget(desc)

        # 主内容区
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # 左侧：报告列表
        left_card = CardWidget()
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(12)

        # 筛选和操作按钮
        filter_layout = QHBoxLayout()
        filter_label = BodyLabel("筛选:")
        filter_layout.addWidget(filter_label)
        self.filter_combo = ComboBox()
        self.filter_combo.addItems(["全部", "PASS", "REVIEW", "FAIL"])
        self.filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_layout.addWidget(self.filter_combo)
        filter_layout.addStretch()

        # 删除选中按钮
        self.delete_btn = PushButton("删除选中")
        self.delete_btn.clicked.connect(self._on_delete_selected)
        self.delete_btn.setEnabled(False)
        filter_layout.addWidget(self.delete_btn)

        clear_btn = PushButton("清空历史")
        clear_btn.clicked.connect(self._on_clear_all)
        filter_layout.addWidget(clear_btn)
        left_layout.addLayout(filter_layout)

        # 报告表格
        self.history_table = TableWidget()
        self.history_table.setColumnCount(4)
        self.history_table.setHorizontalHeaderLabels(["时间", "品牌", "文件数", "状态"])
        self.history_table.horizontalHeader().setStretchLastSection(True)
        self.history_table.setSelectionBehavior(TableWidget.SelectionBehavior.SelectRows)
        self.history_table.cellClicked.connect(self._on_row_clicked)
        left_layout.addWidget(self.history_table)

        # 统计
        self.stats_label = CaptionLabel("共 0 条记录")
        left_layout.addWidget(self.stats_label)

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
        left_layout.addLayout(export_layout)

        content_layout.addWidget(left_card, 2)

        # 右侧：审核报告（直接使用StreamingAuditDisplay，它自带展开按钮）
        self.detail_display = StreamingAuditDisplay(max_height=400)
        self.detail_display.set_title("审核报告")
        self.detail_display.text_edit.setPlaceholderText("请选择一条历史记录查看详情")
        content_layout.addWidget(self.detail_display, 3)

        layout.addLayout(content_layout, 1)

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
        # 统一使用 pass/review/fail 作为内部状态
        grade_to_status = {"PASS": "pass", "REVIEW": "review", "FAIL": "fail"}
        status_to_grade = {"pass": "PASS", "review": "REVIEW", "fail": "FAIL", "warning": "REVIEW"}

        for item in history_list:
            # 优先使用grade字段（新格式），否则从status转换
            grade = item.get("grade", "")
            if grade:
                status = grade_to_status.get(grade, "review")
            else:
                status = item.get("status", "review")
                # 统一 warning 到 review
                if status == "warning":
                    status = "review"
                grade = status_to_grade.get(status, "REVIEW")

            if filter_status != "全部":
                if grade != filter_status:
                    continue

            self.report_files.append({
                'batch_id': item.get("batch_id", ""),
                'time': item.get("time", "-"),
                'brand_name': item.get("brand_name", "-"),
                'file_count': item.get("file_count", 1),
                'score': item.get("score", 0),
                'status': status,
                'grade': grade,
            })

        # 更新表格
        self.history_table.setRowCount(len(self.report_files))

        grade_styles = {
            'PASS': ('#27ae60'),
            'REVIEW': ('#f39c12'),
            'FAIL': ('#e74c3c'),
            '-': ('#95a5a6')
        }

        for row, file_info in enumerate(self.report_files):
            self.history_table.setItem(row, 0, QTableWidgetItem(file_info['time']))
            self.history_table.setItem(row, 1, QTableWidgetItem(file_info.get('brand_name', '-')))
            self.history_table.setItem(row, 2, QTableWidgetItem(str(file_info.get('file_count', 1))))

            grade = file_info.get('grade', '-')
            grade_color = grade_styles.get(grade, '#95a5a6')
            status_item = QTableWidgetItem(grade)
            status_item.setForeground(QColor(grade_color))
            self.history_table.setItem(row, 3, status_item)

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

        # 隐藏展开按钮（单图审核不需要）
        self.detail_display.show_expand_button(False)

        # 读取详细报告
        report_file = self.reports_dir / f"{batch_id}.json"
        if report_file.exists():
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._current_full_report = data

                # 判断是单图还是批量
                if "results" in data:
                    # 批量审核 - 显示HTML表格摘要
                    self._display_batch_html(data)
                elif "report" in data:
                    # 单图审核 - 使用HTML表格格式化
                    report = data.get("report", {})
                    self._display_single_html(report)
                else:
                    self.detail_display.set_text("无法解析报告格式")

            except Exception as e:
                self.detail_display.set_text(f"读取报告失败: {e}")
        else:
            self.detail_display.set_text("报告文件不存在")
            self._current_full_report = None

    def _display_single_html(self, report: dict):
        """将单图审核结果显示为HTML表格"""
        score = report.get("score", 0)
        status = report.get("status", "")
        summary = report.get("summary", "")
        rule_checks = report.get("rule_checks", [])

        # 状态样式 - 仅支持 pass/review/fail
        status_styles = {
            "pass": ("PASS", "#28a745", "#d4edda"),
            "review": ("REVIEW", "#856404", "#fff3cd"),
            "fail": ("FAIL", "#dc3545", "#f8d7da"),
        }
        normalized_status = (status or "review").lower()
        if normalized_status == "warning":
            normalized_status = "review"
        if normalized_status not in status_styles:
            normalized_status = "review"
        status_label, status_color, status_bg = status_styles[normalized_status]

        html_parts = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<meta charset="utf-8">',
            '<style>',
            'html, body { font-family: "Microsoft YaHei", sans-serif; font-size: 13px; margin: 0; padding: 0; width: 100%; height: auto; }',
            'body { display: block; box-sizing: border-box; }',
            '.header { display: flex; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #dee2e6; width: 100%; box-sizing: border-box; }',
            '.score-box { margin-right: 20px; }',
            '.score-value { font-size: 24px; font-weight: bold; color: #333; }',
            '.score-label { font-size: 12px; color: #666; }',
            '.status-badge { padding: 4px 12px; border-radius: 4px; font-weight: bold; font-size: 14px; }',
            '.summary-box { background: #f8f9fa; padding: 10px; border-radius: 6px; margin-bottom: 12px; width: 100%; box-sizing: border-box; }',
            '.summary-title { font-weight: bold; margin-bottom: 6px; color: #333; }',
            '.summary-text { color: #555; line-height: 1.5; }',
            'table { width: 100%; border-collapse: collapse; table-layout: auto; }',
            'th { background: #f1f3f4; padding: 8px 6px; text-align: left; font-weight: bold; border-bottom: 2px solid #dee2e6; font-size: 12px; }',
            'td { padding: 6px; border-bottom: 1px solid #eee; font-size: 12px; }',
            'tr:hover { background: #f8f9fa; }',
            '.rule-id { color: #666; font-family: monospace; width: 70px; }',
            '.rule-content { color: #333; }',
            '.rule-status { text-align: center; width: 60px; }',
            '.badge { padding: 2px 6px; border-radius: 3px; font-size: 11px; font-weight: bold; }',
            '.badge-pass { background: #d4edda; color: #155724; }',
            '.badge-fail { background: #f8d7da; color: #721c24; }',
            '.badge-review { background: #fff3cd; color: #856404; }',
            '.confidence { color: #888; font-size: 11px; text-align: right; width: 50px; }',
            '</style>',
            '</head><body>',
        ]

        html_parts.append('<div class="header">')
        html_parts.append(f'<div class="score-box"><div class="score-value">{score}</div><div class="score-label">分数</div></div>')
        html_parts.append(f'<span class="status-badge" style="background:{status_bg};color:{status_color};">{status_label}</span>')
        html_parts.append('</div>')

        if summary:
            html_parts.append('<div class="summary-box">')
            html_parts.append('<div class="summary-title">总体评价</div>')
            html_parts.append(f'<div class="summary-text">{summary}</div>')
            html_parts.append('</div>')

        if rule_checks:
            # 状态规范化函数：只保留 pass/review/fail 三种状态
            def normalize_status(s):
                if not s:
                    return "review"
                s = s.lower()
                return s if s in ("pass", "fail", "review") else "review"

            status_order = {"fail": 0, "review": 1, "pass": 2}
            def get_sort_key(x):
                rule_id = x.get("rule_id", "Rule_999")
                rule_num = int(rule_id.replace("Rule_", "") or 999)
                normalized = normalize_status(x.get("status"))
                return (status_order.get(normalized, 1), rule_num)
            sorted_checks = sorted(rule_checks, key=get_sort_key)

            html_parts.append('<table>')
            html_parts.append('<tr><th>规则ID</th><th>规则内容</th><th>状态</th><th>置信度</th></tr>')

            for check in sorted_checks:
                rule_id = check.get("rule_id", "")
                rule_content = check.get("rule_content", "") or rule_id
                check_status = (check.get("status") or "review").lower()
                if check_status == "warning":
                    check_status = "review"
                if check_status not in ("pass", "review", "fail"):
                    check_status = "review"
                confidence = check.get("confidence", 0)

                badge_class = f"badge-{check_status}"
                badge_text = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}[check_status]

                html_parts.append('<tr>')
                html_parts.append(f'<td class="rule-id">{rule_id}</td>')
                html_parts.append(f'<td class="rule-content">{rule_content}</td>')
                html_parts.append(f'<td class="rule-status"><span class="badge {badge_class}">{badge_text}</span></td>')
                html_parts.append(f'<td class="confidence">{confidence:.0%}</td>')
                html_parts.append('</tr>')

            html_parts.append('</table>')

        html_parts.append('</body></html>')
        html_content = ''.join(html_parts)

        # 生成纯文本版本用于复制
        text_lines = [f"【审核结果】 分数: {score} | 状态: {status_label}"]
        if summary:
            text_lines.extend(["", "【总体评价】", f"  {summary}"])
        if rule_checks:
            text_lines.extend(["", "【规则检查清单】"])
            # 状态规范化函数：只保留 pass/review/fail 三种状态
            def normalize_status(s):
                if not s:
                    return "review"
                s = s.lower()
                return s if s in ("pass", "fail", "review") else "review"

            status_order = {"fail": 0, "review": 1, "pass": 2}
            def get_sort_key(x):
                rule_id = x.get("rule_id", "Rule_999")
                rule_num = int(rule_id.replace("Rule_", "") or 999)
                normalized = normalize_status(x.get("status"))
                return (status_order.get(normalized, 1), rule_num)
            for check in sorted(rule_checks, key=get_sort_key):
                rule_id = check.get("rule_id", "")
                rule_content = check.get("rule_content", "") or rule_id
                check_status = (check.get("status") or "review").lower()
                if check_status == "warning":
                    check_status = "review"
                if check_status not in ("pass", "review", "fail"):
                    check_status = "review"
                badge_text = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}[check_status]
                confidence = check.get("confidence", 0)
                text_lines.append(f"[{badge_text}] {rule_id}: {rule_content} (置信度: {confidence:.0%})")

        self.detail_display.set_html(html_content, '\n'.join(text_lines))

    def _display_batch_html(self, data: dict):
        """将批量审核结果显示为HTML表格"""
        summary = data.get("summary", {})
        results = data.get("results", [])

        total = summary.get("total", len(results))
        pass_count = summary.get("pass_count", 0)
        # 兼容 warning_count 和 review_count
        review_count = summary.get("review_count", summary.get("warning_count", 0))
        fail_count = summary.get("fail_count", 0)
        error_count = len([r for r in results if r.get("status") == "error"])

        # 计算整体状态
        if fail_count > 0 or error_count > 0:
            overall_status = "FAIL"
        elif review_count > 0:
            overall_status = "REVIEW"
        else:
            overall_status = "PASS"

        status_colors = {
            "pass": "#28a745",
            "review": "#856404",
            "fail": "#dc3545",
            "error": "#6c757d"
        }
        overall_color = status_colors.get(overall_status.lower(), "#6c757d")

        html_parts = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<meta charset="utf-8">',
            '<style>',
            'html, body { font-family: "Microsoft YaHei", sans-serif; font-size: 13px; margin: 0; padding: 0; width: 100%; height: auto; }',
            'body { display: block; box-sizing: border-box; }',
            '.summary { background: #f8f9fa; padding: 12px; border-radius: 6px; margin-bottom: 12px; width: 100%; box-sizing: border-box; }',
            '.summary-title { font-weight: bold; font-size: 14px; margin-bottom: 8px; }',
            '.summary-stats { margin-bottom: 8px; }',
            '.overall-status { font-weight: bold; padding: 4px 12px; border-radius: 4px; color: white; }',
            'table { width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: auto; }',
            'th { background: #e9ecef; padding: 8px 6px; text-align: left; font-weight: bold; border-bottom: 2px solid #dee2e6; font-size: 12px; }',
            'td { padding: 6px; border-bottom: 1px solid #dee2e6; font-size: 12px; }',
            'tr:hover { background: #f8f9fa; }',
            '.status-badge { padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 11px; }',
            '.status-pass { background: #d4edda; color: #155724; }',
            '.status-review { background: #fff3cd; color: #856404; }',
            '.status-fail { background: #f8d7da; color: #721c24; }',
            '.status-error { background: #e2e3e5; color: #383d41; }',
            '.file-name { font-weight: bold; }',
            '.score { font-weight: bold; }',
            '.rule-summary { font-size: 11px; color: #666; }',
            '</style>',
            '</head><body>',
        ]

        # 摘要部分
        html_parts.append('<div class="summary">')
        html_parts.append('<div class="summary-title">批量审核摘要</div>')
        html_parts.append('<div class="summary-stats">')
        html_parts.append(f'总数: {total} | ')
        html_parts.append(f'<span style="color:#28a745;">PASS: {pass_count}</span> | ')
        html_parts.append(f'<span style="color:#856404;">REVIEW: {review_count}</span> | ')
        html_parts.append(f'<span style="color:#dc3545;">FAIL: {fail_count}</span>')
        if error_count > 0:
            html_parts.append(f' | <span style="color:#6c757d;">ERROR: {error_count}</span>')
        html_parts.append('</div>')
        html_parts.append(f'整体状态: <span class="overall-status" style="background:{overall_color};">{overall_status}</span>')
        html_parts.append('</div>')

        # 详细结果表格
        html_parts.append('<div class="summary-title">详细结果</div>')
        html_parts.append('<table>')
        html_parts.append('<tr><th>#</th><th>文件名</th><th>状态</th><th>分数</th><th>FAIL/REVIEW规则</th></tr>')

        for i, r in enumerate(results, 1):
            status = r.get("status", "error")
            status_labels = {"pass": "PASS", "review": "REVIEW", "warning": "REVIEW", "fail": "FAIL", "error": "ERROR"}
            status_label = status_labels.get(status, "?")
            status_class = f"status-{status if status != 'warning' else 'review'}"
            file_name = r.get("file_name", "-")

            report = r.get("report", {})
            score = report.get("score", 0) if report else 0

            rule_checks = report.get("rule_checks", []) if report else []
            fail_count_item = len([c for c in rule_checks if c.get("status") == "fail"])
            review_count_item = len([c for c in rule_checks if c.get("status") in ("review", "warning")])

            # 规则摘要 - 只显示数量
            summary_parts = []
            if fail_count_item > 0:
                summary_parts.append(f'<span style="color:#dc3545;font-weight:bold;">FAIL: {fail_count_item}</span>')
            if review_count_item > 0:
                summary_parts.append(f'<span style="color:#856404;">REVIEW: {review_count_item}</span>')
            if not summary_parts:
                summary_parts.append('<span style="color:#28a745;">全部通过</span>')

            html_parts.append('<tr>')
            html_parts.append(f'<td>{i}</td>')
            html_parts.append(f'<td class="file-name">{file_name}</td>')
            html_parts.append(f'<td><span class="status-badge {status_class}">{status_label}</span></td>')
            html_parts.append(f'<td class="score">{score}</td>')
            html_parts.append(f'<td>{" | ".join(summary_parts)}</td>')
            html_parts.append('</tr>')

        html_parts.append('</table>')
        html_parts.append('</body></html>')
        html_content = ''.join(html_parts)

        # 生成纯文本版本用于复制
        text_lines = [
            f"【批量审核摘要】",
            f"总数: {total} | PASS: {pass_count} | REVIEW: {review_count} | FAIL: {fail_count}",
            f"整体状态: {overall_status}",
            "",
            "【详细结果】"
        ]
        for i, r in enumerate(results, 1):
            status = r.get("status", "error")
            status_labels = {"pass": "PASS", "review": "REVIEW", "warning": "REVIEW", "fail": "FAIL", "error": "ERROR"}
            status_label = status_labels.get(status, "REVIEW")
            file_name = r.get("file_name", "-")
            report = r.get("report", {})
            score = report.get("score", 0) if report else 0

            text_lines.append(f"--- 图片 {i}: {file_name} ---")
            text_lines.append(f"状态: {status_label} | 分数: {score}")

            rule_checks = report.get("rule_checks", []) if report else []
            fail_rules = [c for c in rule_checks if c.get("status") == "fail"]
            review_rules = [c for c in rule_checks if c.get("status") in ("review", "warning")]
            if fail_rules:
                text_lines.append(f"FAIL: {len(fail_rules)}项")
            if review_rules:
                text_lines.append(f"REVIEW: {len(review_rules)}项")
            text_lines.append("")

        self.detail_display.set_html(html_content, '\n'.join(text_lines))

        # 存储批量数据并显示展开按钮（使用StreamingAuditDisplay内置功能）
        batch_data = {
            "results": results,
            "summary": {
                "total": total,
                "pass_count": pass_count,
                "review_count": review_count,
                "fail_count": fail_count
            },
            "status": overall_status.lower()
        }
        self.detail_display.set_batch_data(batch_data, html_content, '\n'.join(text_lines))
        self.detail_display.show_expand_button(True)

    def _audit_to_markdown(self, report: dict) -> str:
        """将审核结果转换为Markdown格式 - 同步导出报告格式"""
        lines = []

        # 评分和状态
        score = report.get("score", 0)
        status = report.get("status", "unknown")

        status_map = {
            "pass": "PASS",
            "warning": "REVIEW",
            "fail": "FAIL",
            "unknown": "?"
        }
        status_text = status_map.get(status, "?")

        lines.append(f"【审核结果】 评分: {score} 分  |  状态: [{status_text}]")
        lines.append("")

        # 总体评价
        summary = report.get("summary", "")
        if summary:
            lines.append("【总体评价】")
            lines.append(f"  {summary}")
            lines.append("")

        # 规则检查清单 - 使用导出报告格式
        rule_checks = report.get("rule_checks", [])
        if rule_checks:
            lines.append("【规则检查清单】")
            lines.append("")

            # 状态规范化函数：只保留 pass/review/fail 三种状态
            def normalize_status(s):
                if not s:
                    return "review"
                s = s.lower()
                return s if s in ("pass", "fail", "review") else "review"

            status_order = {"fail": 0, "review": 1, "pass": 2}
            def get_sort_key(x):
                rule_id = x.get("rule_id", "Rule_999")
                rule_num = int(rule_id.replace("Rule_", "") or 999)
                normalized = normalize_status(x.get("status"))
                return (status_order.get(normalized, 1), rule_num)
            sorted_checks = sorted(rule_checks, key=get_sort_key)

            for check in sorted_checks:
                rule_id = check.get("rule_id", "")
                rule_content = check.get("rule_content", "") or rule_id
                check_status = check.get("status", "pass")
                confidence = check.get("confidence", 0)
                reference = check.get("reference", "")

                # 状态标签
                status_label_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}
                status_label = status_label_map.get(check_status, "?")

                # 导出报告格式: [状态] Rule_ID : 规则内容 -->> 状态 >> 参考文档，置信度：0.XX；
                lines.append(f"[{status_label}] {rule_id} : {rule_content} -->> {status_label} >> {reference}，置信度：{confidence:.2f}；")

            lines.append("")

        return "\n".join(lines)

    def _on_export(self, format_type: str):
        """导出报告"""
        if not hasattr(self, '_current_full_report') or not self._current_full_report:
            InfoBar.warning(
                title="警告",
                content="请先选择一条记录",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
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
                str(export_dir / f"history_export_{timestamp}.md"),
                "Markdown文件 (*.md)"
            )
            if file_path:
                md_content = self._report_to_markdown(self._current_full_report)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                InfoBar.success(
                    title="成功",
                    content=f"已导出到:\n{file_path}",
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )

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
                f"- PASS: {summary.get('pass_count', 0)}",
                f"- REVIEW: {summary.get('warning_count', 0)}",
                f"- FAIL: {summary.get('fail_count', 0)}",
                "",
            ])

            # 详细结果 - 包含完整的每张图片报告
            for i, r in enumerate(data.get("results", []), 1):
                lines.append(f"## 图片 {i}: {r.get('file_name', '-')}")
                lines.append("")

                report = r.get("report", {})
                if report:
                    status_map = {"pass": "PASS", "warning": "REVIEW", "fail": "FAIL", "error": "ERROR"}
                    status = status_map.get(r.get("status"), "?")
                    lines.append(f"**状态**: {status}")
                    lines.append("")

                    # 规则检查清单
                    rule_checks = report.get("rule_checks", [])
                    if rule_checks:
                        lines.append("## 规则检查清单")
                        lines.append("")

                        # 状态规范化函数：只保留 pass/review/fail 三种状态
                        def normalize_status(s):
                            if not s:
                                return "review"
                            s = s.lower()
                            return s if s in ("pass", "fail", "review") else "review"

                        status_order = {"fail": 0, "review": 1, "pass": 2}
                        def get_sort_key(x):
                            rule_id = x.get("rule_id", "Rule_999")
                            rule_num = int(rule_id.replace("Rule_", "") or 999)
                            normalized = normalize_status(x.get("status"))
                            return (status_order.get(normalized, 1), rule_num)
                        sorted_checks = sorted(rule_checks, key=get_sort_key)

                        for check in sorted_checks:
                            check_status = check.get("status", "review")
                            status_label_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW", "warn": "REVIEW"}
                            status_label = status_label_map.get(check_status, check_status.upper())
                            confidence = check.get("confidence", 0)
                            lines.append(f"[{status_label}] {check.get('rule_id', '')} : {check.get('rule_content', '')} -->> {status_label} >> {check.get('reference', '')}，置信度：{confidence:.2f}；")
                        lines.append("")

                lines.append("---")
                lines.append("")

        elif "report" in data:
            # 单图报告
            report = data.get("report", {})
            status_map = {"pass": "PASS", "warning": "REVIEW", "fail": "FAIL"}
            status = status_map.get(report.get("status"), "?")
            lines.extend([
                f"**状态**: {status}",
                "",
            ])

            # 规则检查清单
            rule_checks = report.get("rule_checks", [])
            if rule_checks:
                lines.append("## 规则检查清单")
                lines.append("")

                # 状态规范化函数：只保留 pass/review/fail 三种状态
                def normalize_status(s):
                    if not s:
                        return "review"
                    s = s.lower()
                    return s if s in ("pass", "fail", "review") else "review"

                status_order = {"fail": 0, "review": 1, "pass": 2}
                def get_sort_key(x):
                    rule_id = x.get("rule_id", "Rule_999")
                    rule_num = int(rule_id.replace("Rule_", "") or 999)
                    normalized = normalize_status(x.get("status"))
                    return (status_order.get(normalized, 1), rule_num)
                sorted_checks = sorted(rule_checks, key=get_sort_key)

                for check in sorted_checks:
                    check_status = check.get("status", "review")
                    status_label_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW", "warn": "REVIEW"}
                    status_label = status_label_map.get(check_status, check_status.upper())
                    confidence = check.get("confidence", 0)
                    lines.append(f"[{status_label}] {check.get('rule_id', '')} : {check.get('rule_content', '')} -->> {status_label} >> {check.get('reference', '')}，置信度：{confidence:.2f}；")
                lines.append("")

        return "\n".join(lines)

    def _on_delete_selected(self):
        """删除选中的记录"""
        if not self.current_report:
            InfoBar.warning(
                title="警告",
                content="请先选择要删除的记录",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        batch_id = self.current_report.get("batch_id", "")
        if not batch_id:
            InfoBar.warning(
                title="警告",
                content="无法获取记录ID",
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
            return

        box = MessageBox(
            "确认删除",
            f"确定要删除这条记录吗？\n时间: {self.current_report.get('time', '-')}\n品牌: {self.current_report.get('brand_name', '-')}",
            self
        )
        box.yesButton.setText("确定")
        box.cancelButton.setText("取消")

        if box.exec():
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
            self.detail_display.clear()
            self.delete_btn.setEnabled(False)
            self.export_json_btn.setEnabled(False)
            self.export_md_btn.setEnabled(False)

            # 刷新列表并更新统计
            self.refresh()
            InfoBar.success(
                title="成功",
                content="记录已删除",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )

    def _on_clear_all(self):
        """清空所有历史"""
        box = MessageBox(
            "确认清空",
            "确定要清空所有历史记录吗？\n此操作不可恢复！",
            self
        )
        box.yesButton.setText("确定")
        box.cancelButton.setText("取消")

        if box.exec():
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
            self.detail_display.clear()
            self._current_full_report = None
            InfoBar.success(
                title="成功",
                content="历史记录已清空",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )