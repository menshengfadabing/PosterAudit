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
        self.filter_combo.addItems(["全部", "通过", "需修改", "不通过"])
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
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels(["时间", "品牌", "文件数", "评级", "状态"])
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

        content_layout.addWidget(left_card, 1)

        # 右侧：报告详情
        right_card = CardWidget()
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(12)

        detail_title = StrongBodyLabel("报告详情")
        right_layout.addWidget(detail_title)

        # 摘要区域
        summary_card = CardWidget()
        summary_card.setBorderRadius(8)
        summary_layout = QGridLayout(summary_card)
        summary_layout.setContentsMargins(16, 16, 16, 16)
        summary_layout.setSpacing(12)

        time_lbl = BodyLabel("时间:")
        brand_lbl = BodyLabel("品牌:")
        grade_lbl = BodyLabel("评级:")
        status_lbl = BodyLabel("状态:")

        self.time_label = BodyLabel("--")
        self.brand_label = BodyLabel("--")
        self.grade_label = BodyLabel("--")
        self.status_label = BodyLabel("--")

        summary_layout.addWidget(time_lbl, 0, 0)
        summary_layout.addWidget(self.time_label, 0, 1)
        summary_layout.addWidget(brand_lbl, 0, 2)
        summary_layout.addWidget(self.brand_label, 0, 3)
        summary_layout.addWidget(grade_lbl, 1, 0)
        summary_layout.addWidget(self.grade_label, 1, 1)
        summary_layout.addWidget(status_lbl, 1, 2)
        summary_layout.addWidget(self.status_label, 1, 3)

        right_layout.addWidget(summary_card)

        # 详细内容
        self.detail_text = TextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setPlaceholderText("选择一条记录查看详情...")
        right_layout.addWidget(self.detail_text, 1)

        # 提示信息
        hint_label = CaptionLabel("上方显示简化结果，完整报告请点击导出JSON或Markdown")
        hint_label.setWordWrap(True)
        right_layout.addWidget(hint_label)

        content_layout.addWidget(right_card, 1)

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

            # 显示评级而非分数
            status = file_info.get('status', 'unknown')
            grade_map = {'pass': '优', 'warning': '良', 'fail': '差', 'completed': '优', 'unknown': '-'}
            grade_colors = {'pass': '#27ae60', 'warning': '#f39c12', 'fail': '#e74c3c', 'completed': '#27ae60', 'unknown': '#95a5a6'}
            grade = grade_map.get(status, '-')
            grade_item = QTableWidgetItem(grade)
            grade_item.setForeground(QColor(grade_colors.get(status, '#95a5a6')))
            self.history_table.setItem(row, 3, grade_item)

            status_styles = {
                'pass': ('通过', '#27ae60'),
                'warning': ('需修改', '#f39c12'),
                'fail': ('不通过', '#e74c3c'),
                'completed': ('完成', '#27ae60'),
                'unknown': ('未知', '#95a5a6')
            }
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

        # 显示评级
        status = file_info.get("status", "unknown")
        grade_map = {'pass': '优', 'warning': '良', 'fail': '差', 'completed': '优', 'unknown': '-'}
        self.grade_label.setText(grade_map.get(status, "-"))
        self.status_label.setText(status)

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
        """渲染报告详情 - 只显示规则检查清单"""
        lines = []
        grade_map = {'pass': '优', 'warning': '良', 'fail': '差', 'error': '错误'}

        # 判断是单图还是批量
        if "results" in data:
            # 批量审核
            summary = data.get("summary", {})
            lines.append("【批量审核摘要】")
            lines.append(f"总数: {summary.get('total', 0)}")
            lines.append(f"优: {summary.get('pass_count', 0)}")
            lines.append(f"良: {summary.get('warning_count', 0)}")
            lines.append(f"差: {summary.get('fail_count', 0)}")
            lines.append("")

            results = data.get("results", [])
            if results:
                lines.append(f"【详细结果 ({len(results)}项)】")
                lines.append("")

                for i, r in enumerate(results):
                    status_icon = {"pass": "✅", "warning": "⚠️", "fail": "❌", "error": "❌"}.get(r.get("status"), "❌")
                    grade = grade_map.get(r.get("status"), "?")
                    lines.append(f"--- 图片 {i+1}: {r.get('file_name', '-')} ---")
                    lines.append(f"状态: {status_icon} | 评级: {grade}")
                    lines.append("")

                    report = r.get("report", {})
                    if report:
                        # 规则检查清单
                        rule_checks = report.get("rule_checks", [])
                        if rule_checks:
                            lines.append("【规则检查清单】")
                            fail_count = len([c for c in rule_checks if c.get("status") == "fail"])
                            review_count = len([c for c in rule_checks if c.get("status") in ("review", "warn")])
                            pass_count = len([c for c in rule_checks if c.get("status") == "pass"])
                            lines.append(f"通过:{pass_count} 不合规:{fail_count} 需复核:{review_count}")
                            lines.append("")

                            # 按状态排序
                            status_order = {"fail": 0, "review": 1, "warn": 1, "pass": 2}
                            sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))
                            for check in sorted_checks:
                                status = check.get("status", "review")
                                if status == "pass":
                                    icon = "✅"
                                else:
                                    icon = "❌"
                                result_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW", "warn": "WARN"}
                                result = result_map.get(status, status.upper())
                                lines.append(f"{icon} {check.get('rule_id', '')} : {check.get('rule_content', '')} -->> {result}")
                            lines.append("")

                    lines.append("")

        elif "report" in data:
            # 单图审核
            report = data.get("report", {})
            status_icon = {"pass": "✅", "warning": "⚠️", "fail": "❌"}.get(report.get("status"), "❌")
            grade = grade_map.get(report.get("status"), "?")
            lines.append(f"【审核结果】评级: {grade} | 状态: {status_icon}")
            lines.append("")

            # 规则检查清单
            rule_checks = report.get("rule_checks", [])
            if rule_checks:
                lines.append("【规则检查清单】")
                fail_count = len([c for c in rule_checks if c.get("status") == "fail"])
                review_count = len([c for c in rule_checks if c.get("status") in ("review", "warn")])
                pass_count = len([c for c in rule_checks if c.get("status") == "pass"])
                lines.append(f"通过:{pass_count} 不合规:{fail_count} 需复核:{review_count}")
                lines.append("")

                # 按状态排序
                status_order = {"fail": 0, "review": 1, "warn": 1, "pass": 2}
                sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

                for check in sorted_checks:
                    status = check.get("status", "review")
                    if status == "pass":
                        icon = "✅"
                    else:
                        icon = "❌"
                    result_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW", "warn": "WARN"}
                    result = result_map.get(status, status.upper())
                    confidence = check.get("confidence", 0)
                    lines.append(f"{icon} {check.get('rule_id', '')} : {check.get('rule_content', '')} -->> {result} >> {check.get('reference', '')}，置信度：{confidence:.2f}；")

        self.detail_text.setText("\n".join(lines))

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
                f"- 优: {summary.get('pass_count', 0)}",
                f"- 良: {summary.get('warning_count', 0)}",
                f"- 差: {summary.get('fail_count', 0)}",
                "",
            ])

            # 详细结果 - 包含完整的每张图片报告
            for i, r in enumerate(data.get("results", []), 1):
                lines.append(f"## 图片 {i}: {r.get('file_name', '-')}")
                lines.append("")

                report = r.get("report", {})
                if report:
                    status_map = {"pass": "✅ 通过", "warning": "⚠️ 需修改", "fail": "❌ 不通过", "error": "❌ 错误"}
                    grade_map = {"pass": "优", "warning": "良", "fail": "差", "error": "错误"}
                    grade = grade_map.get(r.get("status"), "?")
                    lines.append(f"**评级**: {grade}")
                    lines.append(f"**状态**: {status_map.get(r.get('status'), r.get('status', '-'))}")
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
                            status = check.get("status", "review")
                            if status == "pass":
                                icon = "✅"
                            else:
                                icon = "❌"
                            result_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW", "warn": "WARN"}
                            result = result_map.get(status, status.upper())
                            confidence = check.get("confidence", 0)
                            lines.append(f"[{icon}] {check.get('rule_id', '')} : {check.get('rule_content', '')} -->> {result} >> {check.get('reference', '')}，置信度：{confidence:.2f}；")
                        lines.append("")

                lines.append("---")
                lines.append("")

        elif "report" in data:
            # 单图报告
            report = data.get("report", {})
            status_map = {"pass": "✅ 通过", "warning": "⚠️ 需修改", "fail": "❌ 不通过"}
            grade_map = {"pass": "优", "warning": "良", "fail": "差"}
            grade = grade_map.get(report.get("status"), "?")
            lines.extend([
                f"**评级**: {grade}",
                f"**状态**: {status_map.get(report.get('status'), report.get('status', '-'))}",
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
                    status = check.get("status", "review")
                    if status == "pass":
                        icon = "✅"
                    else:
                        icon = "❌"
                    result_map = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW", "warn": "WARN"}
                    result = result_map.get(status, status.upper())
                    confidence = check.get("confidence", 0)
                    lines.append(f"[{icon}] {check.get('rule_id', '')} : {check.get('rule_content', '')} -->> {result} >> {check.get('reference', '')}，置信度：{confidence:.2f}；")
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
            self.detail_text.clear()
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
            self.detail_text.clear()
            self._current_full_report = None
            InfoBar.success(
                title="成功",
                content="历史记录已清空",
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )