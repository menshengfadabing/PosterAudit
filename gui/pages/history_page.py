"""报告历史页面（Fluent风格）"""

import json
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFileDialog
from PySide6.QtGui import QColor

from qfluentwidgets import (
    ScrollArea, StrongBodyLabel, CaptionLabel, BodyLabel,
    PushButton, PrimaryPushButton, ComboBox, TextEdit,
    TableWidget, InfoBar, InfoBarPosition,
    MessageBox, CardWidget, TitleLabel, SubtitleLabel
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

        # 右侧：审核报告（直接放置detail_display）
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
        status_map = {"PASS": "pass", "REVIEW": "warning", "FAIL": "fail"}

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
            'pass': ('PASS', '#27ae60'),
            'warning': ('REVIEW', '#f39c12'),
            'fail': ('FAIL', '#e74c3c'),
            'completed': ('PASS', '#27ae60'),
            'unknown': ('-', '#95a5a6')
        }

        for row, file_info in enumerate(self.report_files):
            self.history_table.setItem(row, 0, QTableWidgetItem(file_info['time']))
            self.history_table.setItem(row, 1, QTableWidgetItem(file_info.get('brand_name', '-')))
            self.history_table.setItem(row, 2, QTableWidgetItem(str(file_info.get('file_count', 1))))

            status = file_info.get('status', 'unknown')
            status_text, status_color = status_styles.get(status, ('-', '#95a5a6'))
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(QColor(status_color))
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

        # 读取详细报告
        report_file = self.reports_dir / f"{batch_id}.json"
        if report_file.exists():
            try:
                with open(report_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._current_full_report = data

                # 判断是单图还是批量
                if "results" in data:
                    # 批量审核 - 显示摘要
                    self._display_batch_summary(data)
                elif "report" in data:
                    # 单图审核 - 使用_audit_to_markdown格式化
                    report = data.get("report", {})
                    markdown = self._audit_to_markdown(report)
                    self.detail_display.set_text(markdown)
                else:
                    self.detail_display.set_text("无法解析报告格式")

            except Exception as e:
                self.detail_display.set_text(f"读取报告失败: {e}")
        else:
            self.detail_display.set_text("报告文件不存在")
            self._current_full_report = None

    def _display_batch_summary(self, data: dict):
        """显示批量审核摘要 - 同步导出报告格式"""
        summary = data.get("summary", {})
        results = data.get("results", [])

        lines = []
        lines.append(f"【批量审核摘要】")
        lines.append(f"总数: {summary.get('total', 0)} | PASS: {summary.get('pass_count', 0)} | REVIEW: {summary.get('warning_count', 0)} | FAIL: {summary.get('fail_count', 0)}")
        lines.append("")

        if results:
            lines.append(f"【详细结果 ({len(results)}项)】")
            lines.append("")

            for i, r in enumerate(results, 1):
                status_icon_map = {"pass": "[PASS]", "warning": "[REVIEW]", "fail": "[FAIL]", "error": "[ERROR]"}
                status_label = status_icon_map.get(r.get("status"), "[?]")

                lines.append(f"--- 图片 {i}: {r.get('file_name', '-')} ---")
                lines.append(f"状态: {status_label}")

                report = r.get("report", {})
                if r.get("status") == "error":
                    lines.append(f"错误: {r.get('error', '未知错误')}")
                    lines.append("")
                    continue

                if report:
                    # 显示分数
                    score = report.get("score", 0)
                    if score:
                        lines.append(f"分数: {score}")

                    # 显示详细规则检查 - 使用导出报告格式
                    rule_checks = report.get("rule_checks", [])
                    if rule_checks:
                        # 按状态排序: fail > review > pass
                        status_order = {"fail": 0, "review": 1, "pass": 2}
                        sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

                        for check in sorted_checks:
                            rule_id = check.get("rule_id", "")
                            rule_content = check.get("rule_content", "") or rule_id
                            check_status = check.get("status", "pass")
                            confidence = check.get("confidence", 0)
                            reference = check.get("reference", "")

                            # 状态标签
                            status_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}
                            check_status_label = status_map.get(check_status, "?")

                            # 导出报告格式: [状态] Rule_ID : 规则内容 -->> 状态 >> 参考文档，置信度：0.XX；
                            lines.append(f"[{check_status_label}] {rule_id} : {rule_content} -->> {check_status_label} >> {reference}，置信度：{confidence:.2f}；")

                lines.append("")

        self.detail_display.set_text("\n".join(lines))

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

            # 按状态排序: fail > review > pass
            status_order = {"fail": 0, "review": 1, "pass": 2}
            sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status", "pass"), 3))

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

                        # 按状态排序
                        status_order = {"fail": 0, "review": 1, "pass": 2, "warn": 1}
                        sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

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

                # 按状态排序
                status_order = {"fail": 0, "review": 1, "pass": 2, "warn": 1}
                sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

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