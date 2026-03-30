"""流式文本显示组件 - 用于实时显示LLM输出"""

import json
import re
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtGui import QTextCursor, QFont

from qfluentwidgets import (
    TextEdit, PushButton, CaptionLabel, BodyLabel, FluentIcon as FIF,
    CardWidget
)


class StreamingTextDisplay(CardWidget):
    """
    流式文本显示组件

    用于实时显示LLM流式输出的文本内容。
    支持：
    - 追加文本（自动滚动到底部）
    - 清空文本
    - 复制内容
    - 显示/隐藏控制
    - 导出按钮支持
    """

    # 文本更新信号
    text_appended = Signal(str)
    cleared = Signal()

    def __init__(self, parent=None, title: str = "AI 输出", max_height: int = 300, show_export: bool = False):
        super().__init__(parent)
        self._title = title
        self._max_height = max_height
        self._is_streaming = False
        self._streaming_text = ""  # 累积的流式文本
        self._raw_json = ""  # 原始JSON数据
        self._show_export = show_export

        self._init_ui()

    def _init_ui(self):
        """初始化UI"""
        self.setBorderRadius(8)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 标题栏
        header_layout = QHBoxLayout()

        self.title_label = CaptionLabel(self._title)
        self.title_label.setStyleSheet("color: #666; font-weight: bold;")
        header_layout.addWidget(self.title_label)

        # 状态指示
        self.status_label = CaptionLabel("")
        self.status_label.setStyleSheet("color: #0078d4;")
        header_layout.addWidget(self.status_label)

        header_layout.addStretch()

        # 清空按钮
        self.clear_btn = PushButton("清空")
        self.clear_btn.setIcon(FIF.DELETE)
        self.clear_btn.setFixedHeight(28)
        self.clear_btn.clicked.connect(self.clear)
        header_layout.addWidget(self.clear_btn)

        # 复制按钮
        self.copy_btn = PushButton("复制")
        self.copy_btn.setIcon(FIF.COPY)
        self.copy_btn.setFixedHeight(28)
        self.copy_btn.clicked.connect(self._copy_content)
        header_layout.addWidget(self.copy_btn)

        layout.addLayout(header_layout)

        # 文本显示区域
        self.text_edit = TextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumHeight(self._max_height)
        self.text_edit.setPlaceholderText("等待AI输出...")
        self.text_edit.setStyleSheet("""
            TextEdit {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', 'Microsoft YaHei Mono', monospace;
                font-size: 13px;
                line-height: 1.5;
            }
        """)
        layout.addWidget(self.text_edit)

        # 导出按钮行（可选）
        if self._show_export:
            export_layout = QHBoxLayout()
            export_layout.addStretch()

            self.export_json_btn = PushButton("导出JSON")
            self.export_json_btn.setIcon(FIF.SAVE)
            self.export_json_btn.setFixedHeight(28)
            self.export_json_btn.setEnabled(False)
            export_layout.addWidget(self.export_json_btn)

            self.export_md_btn = PushButton("导出Markdown")
            self.export_md_btn.setIcon(FIF.DOCUMENT)
            self.export_md_btn.setFixedHeight(28)
            self.export_md_btn.setEnabled(False)
            export_layout.addWidget(self.export_md_btn)

            layout.addLayout(export_layout)

        # 始终可见，不隐藏
        # self.setVisible(False)

    def set_export_enabled(self, enabled: bool):
        """设置导出按钮是否可用"""
        if self._show_export:
            self.export_json_btn.setEnabled(enabled)
            self.export_md_btn.setEnabled(enabled)

    def set_export_callbacks(self, json_callback, md_callback):
        """设置导出回调"""
        if self._show_export:
            self.export_json_btn.clicked.connect(json_callback)
            self.export_md_btn.clicked.connect(md_callback)

    @Slot(str)
    def append_text(self, text: str):
        """
        追加文本到显示区域

        Args:
            text: 要追加的文本
        """
        # 累积文本
        self._streaming_text += text

        # 移动光标到末尾并插入文本
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.text_edit.setTextCursor(cursor)

        # 不自动滚动，让用户可以自由查看
        # self.text_edit.ensureCursorVisible()

        # 发送信号
        self.text_appended.emit(text)

    @Slot(str)
    def set_text(self, text: str):
        """
        设置全部文本（替换原有内容）

        Args:
            text: 新的文本内容
        """
        self._streaming_text = text
        self.text_edit.setPlainText(text)

        # 滚动到底部
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.text_edit.setTextCursor(cursor)

    def set_html(self, html: str, plain_text: str = None):
        """
        设置HTML内容，同时保留纯文本版本用于复制

        Args:
            html: HTML内容
            plain_text: 可选的纯文本内容，如果不提供则尝试从HTML提取
        """
        self.text_edit.setHtml(html)
        if plain_text:
            self._streaming_text = plain_text
        else:
            # 从HTML中提取纯文本
            self._streaming_text = self.text_edit.toPlainText()

    @Slot()
    def clear(self):
        """清空文本"""
        self._streaming_text = ""
        self._raw_json = ""
        self.text_edit.clear()
        self._is_streaming = False
        self.status_label.setText("")
        self.cleared.emit()

    @Slot(str)
    def start_streaming(self, status: str = "正在生成..."):
        """
        开始流式输出

        Args:
            status: 状态文本
        """
        self._is_streaming = True
        self.status_label.setText(status)
        self.clear()

    @Slot(str)
    def stop_streaming(self, status: str = ""):
        """
        停止流式输出

        Args:
            status: 完成状态文本
        """
        self._is_streaming = False
        if status:
            self.status_label.setText(status)
        else:
            self.status_label.setText("生成完成")

    @Slot()
    def is_streaming(self) -> bool:
        """是否正在流式输出"""
        return self._is_streaming

    @Slot()
    def get_text(self) -> str:
        """获取当前全部文本"""
        return self._streaming_text

    @Slot()
    def _copy_content(self):
        """复制内容到剪贴板"""
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(self._streaming_text)

        # 显示复制成功提示
        self.status_label.setText("已复制到剪贴板")
        QTimer.singleShot(2000, lambda: self.status_label.setText("生成完成") if not self._is_streaming else None)

    @Slot(str)
    def set_title(self, title: str):
        """设置标题"""
        self._title = title
        self.title_label.setText(title)


class StreamingJsonDisplay(StreamingTextDisplay):
    """
    流式JSON显示组件

    在流式输出完成后，尝试解析JSON并格式化显示
    """

    def __init__(self, parent=None, title: str = "AI 输出", max_height: int = 300):
        super().__init__(parent, title, max_height)

    @Slot(str)
    def stop_streaming(self, status: str = ""):
        """
        停止流式输出，尝试解析JSON
        """
        super().stop_streaming(status)

        # 尝试解析并格式化JSON
        self._try_format_json()

    def _try_format_json(self):
        """尝试解析并格式化JSON"""
        try:
            text = self._streaming_text.strip()
            data = self._parse_json(text)

            if data:
                self._raw_json = json.dumps(data, ensure_ascii=False, indent=2)
                # 格式化显示
                formatted = json.dumps(data, ensure_ascii=False, indent=2)
                self.text_edit.setPlainText(formatted)
                self._streaming_text = formatted

        except Exception:
            # 解析失败，保持原样
            pass

    def _parse_json(self, text: str) -> Optional[dict]:
        """解析JSON文本"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取JSON块
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试找到第一个 { 和最后一个 }
        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        return None

    def get_parsed_json(self) -> Optional[dict]:
        """获取解析后的JSON对象"""
        if self._raw_json:
            try:
                return json.loads(self._raw_json)
            except:
                pass
        return self._parse_json(self._streaming_text)


class StreamingRulesDisplay(StreamingTextDisplay):
    """
    流式规范解析显示组件

    输出JSON，完成后自动转换为可读的Markdown格式
    """

    def __init__(self, parent=None, max_height: int = 400, show_export: bool = False):
        super().__init__(parent, "AI 规范解析", max_height, show_export)
        self.setMaximumHeight(9999)  # 不限制组件高度
        self.text_edit.setMaximumHeight(9999)  # 不限制文本框高度

    @Slot(str)
    def stop_streaming(self, status: str = ""):
        """
        停止流式输出，转换为Markdown格式显示
        """
        super().stop_streaming(status)

        # 尝试解析并转换为Markdown
        try:
            text = self._streaming_text.strip()
            data = self._parse_json(text)

            if data:
                self._raw_json = json.dumps(data, ensure_ascii=False, indent=2)
                markdown = self._rules_to_markdown(data)
                self.text_edit.setPlainText(markdown)
                self._streaming_text = markdown

                # 切换样式为普通文本
                self.text_edit.setStyleSheet("""
                    TextEdit {
                        background-color: #fafafa;
                        border: 1px solid #e0e0e0;
                        border-radius: 4px;
                        padding: 12px;
                        font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;
                        font-size: 14px;
                        line-height: 1.6;
                    }
                """)
        except Exception:
            # 解析失败，保持原样
            pass

    def _parse_json(self, text: str) -> Optional[dict]:
        """解析JSON文本"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _rules_to_markdown(self, data: dict) -> str:
        """将规范JSON转换为Markdown格式"""
        lines = []

        # 品牌名称
        brand_name = data.get("brand_name", "未命名品牌")
        lines.append(f"【品牌名称】{brand_name}")
        lines.append("")

        # === 主要规范 ===

        # 色彩规范
        color = data.get("color", {})
        if color and (color.get("primary") or color.get("secondary") or color.get("forbidden") or color.get("additional_rules")):
            lines.append("【色彩规范】")
            if color.get("description"):
                lines.append(f"  描述: {color['description']}")

            if color.get("primary"):
                p = color["primary"]
                lines.append(f"  主色: {p.get('value', '')} ({p.get('name', '主色')})")

            if color.get("secondary"):
                for i, c in enumerate(color["secondary"], 1):
                    lines.append(f"  辅助色{i}: {c.get('value', '')} ({c.get('name', '')})")

            if color.get("forbidden"):
                for c in color["forbidden"]:
                    reason = f" - {c.get('reason')}" if c.get("reason") else ""
                    lines.append(f"  禁用色: {c.get('value', '')} ({c.get('name', '')}){reason}")

            if color.get("additional_rules"):
                for rule in color["additional_rules"]:
                    lines.append(f"  • {rule}")
            lines.append("")

        # Logo规范
        logo = data.get("logo", {})
        if logo and (logo.get("position_description") or logo.get("additional_rules") or logo.get("color_requirements")):
            lines.append("【Logo规范】")
            lines.append(f"  位置: {logo.get('position_description', '未指定')}")

            if logo.get("size_range"):
                lines.append(f"  尺寸: {logo['size_range'].get('min', 5)}% - {logo['size_range'].get('max', 15)}%")

            lines.append(f"  安全间距: {logo.get('safe_margin_px', 20)}px")

            if logo.get("min_display_ratio"):
                lines.append(f"  最小显示比例: {logo['min_display_ratio']}")

            if logo.get("color_requirements"):
                lines.append("  颜色要求:")
                for req in logo["color_requirements"]:
                    lines.append(f"    • {req}")

            if logo.get("background_requirements"):
                lines.append("  背景要求:")
                for req in logo["background_requirements"]:
                    lines.append(f"    • {req}")

            if logo.get("additional_rules"):
                lines.append("  其他规则:")
                for rule in logo["additional_rules"]:
                    lines.append(f"    • {rule}")
            lines.append("")

        # 字体规范
        font = data.get("font", {})
        if font and (font.get("allowed") or font.get("forbidden") or font.get("additional_rules")):
            lines.append("【字体规范】")
            if font.get("allowed"):
                lines.append(f"  允许: {', '.join(font['allowed'])}")
            if font.get("forbidden"):
                lines.append(f"  禁用: {', '.join(font['forbidden'])}")
            if font.get("size_rules"):
                for key, val in font["size_rules"].items():
                    lines.append(f"  {key}: {val}")
            if font.get("note"):
                lines.append(f"  备注: {font['note']}")
            if font.get("additional_rules"):
                for rule in font["additional_rules"]:
                    lines.append(f"  • {rule}")
            lines.append("")

        # === 次要规范 ===
        secondary_rules = data.get("secondary_rules", [])
        if secondary_rules:
            lines.append("【次要规范】")

            # 按分类分组
            categories = {}
            for rule in secondary_rules:
                cat = rule.get("category", "其他")
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(rule)

            for category, rules_list in categories.items():
                lines.append(f"  {category}:")
                for rule in sorted(rules_list, key=lambda x: x.get("priority", 1)):
                    lines.append(f"    - {rule.get('name', '')}: {rule.get('content', '')}")
            lines.append("")

        return "\n".join(lines)

    def get_parsed_json(self) -> Optional[dict]:
        """获取解析后的JSON对象"""
        if self._raw_json:
            try:
                return json.loads(self._raw_json)
            except:
                pass
        return None


class StreamingAuditDisplay(StreamingTextDisplay):
    """
    流式审核结果显示组件

    输出JSON，完成后自动转换为HTML表格格式审核报告
    支持批量结果的展开/折叠功能
    """

    # 展开状态变化信号
    expand_changed = Signal(bool)

    def __init__(self, parent=None, max_height: int = 400, show_export: bool = False):
        super().__init__(parent, "AI 审核输出", max_height, show_export)
        self.setMaximumHeight(9999)  # 不限制组件高度
        self.text_edit.setMaximumHeight(9999)  # 不限制文本框高度
        self._batch_data = None  # 存储批量审核原始数据
        self._is_expanded = False  # 当前是否展开状态

        # 创建展开按钮并插入到清空按钮左边
        self._expand_btn = PushButton("展开详情")
        self._expand_btn.setIcon(FIF.VIEW)
        self._expand_btn.setFixedHeight(28)
        self._expand_btn.clicked.connect(self._toggle_expand)
        self._expand_btn.setVisible(False)  # 默认隐藏，批量审核时显示

        # 获取标题栏布局并插入展开按钮
        header_layout = self.layout().itemAt(0)
        if header_layout:
            # 在清空按钮之前插入展开按钮（索引3：标题、状态、stretch、清空、复制）
            header_layout.insertWidget(3, self._expand_btn)

    def show_expand_button(self, show: bool = True):
        """显示/隐藏展开按钮"""
        if self._expand_btn:
            self._expand_btn.setVisible(show)
            if show:
                self._expand_btn.setText("展开详情")
                self._is_expanded = False

    def _toggle_expand(self):
        """切换展开/折叠状态"""
        if not self._batch_data:
            return

        self._is_expanded = not self._is_expanded

        if self._is_expanded:
            # 展开显示详细规则
            html = self._batch_to_expanded_html(self._batch_data)
            text = self._batch_to_expanded_text(self._batch_data)
            self._expand_btn.setText("折叠摘要")
        else:
            # 折叠显示摘要表格
            html = self._batch_data.get("_summary_html", "")
            text = self._batch_data.get("_summary_text", "")
            self._expand_btn.setText("展开详情")

        if html:
            self.set_html(html, text)

        self.expand_changed.emit(self._is_expanded)

    def set_batch_data(self, data: dict, summary_html: str, summary_text: str):
        """设置批量审核数据，用于展开/折叠"""
        self._batch_data = data
        self._batch_data["_summary_html"] = summary_html
        self._batch_data["_summary_text"] = summary_text

    def _batch_to_expanded_html(self, data: dict) -> str:
        """将批量审核结果展开为详细HTML"""
        results = data.get("results", [])
        summary = data.get("summary", {})

        total = summary.get("total", len(results))
        pass_count = summary.get("pass_count", 0)
        review_count = summary.get("review_count", summary.get("warning_count", 0))
        fail_count = summary.get("fail_count", 0)

        # 计算整体状态
        overall_status = data.get("status", "review")
        if fail_count > 0:
            overall_status = "fail"
        elif review_count > 0:
            overall_status = "review"
        else:
            overall_status = "pass"

        status_colors = {
            "pass": "#28a745",
            "review": "#856404",
            "fail": "#dc3545"
        }
        overall_color = status_colors.get(overall_status, "#856404")

        html_parts = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<meta charset="utf-8">',
            '<style>',
            'body { font-family: "Microsoft YaHei", sans-serif; font-size: 13px; margin: 0; padding: 0; width: 100%; }',
            '.batch-header { background: #f8f9fa; padding: 12px; border-radius: 6px; margin-bottom: 16px; }',
            '.batch-title { font-weight: bold; font-size: 15px; margin-bottom: 8px; }',
            '.batch-stats { font-size: 13px; }',
            '.overall-badge { padding: 4px 12px; border-radius: 4px; font-weight: bold; color: white; margin-left: 10px; }',
            '.image-section { margin-bottom: 20px; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px; background: #fff; }',
            '.image-header { display: flex; align-items: center; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #eee; }',
            '.image-title { font-weight: bold; font-size: 14px; color: #333; }',
            '.image-status { padding: 2px 8px; border-radius: 3px; font-weight: bold; font-size: 12px; margin-left: 10px; }',
            '.image-score { margin-left: 15px; color: #666; }',
            '.status-pass { background: #d4edda; color: #155724; }',
            '.status-review { background: #fff3cd; color: #856404; }',
            '.status-fail { background: #f8d7da; color: #721c24; }',
            '.status-error { background: #e2e3e5; color: #383d41; }',
            'table { width: 100%; border-collapse: collapse; margin-top: 8px; }',
            'th { background: #f1f3f4; padding: 6px 4px; text-align: left; font-weight: bold; border-bottom: 2px solid #dee2e6; font-size: 12px; }',
            'td { padding: 5px 4px; border-bottom: 1px solid #eee; font-size: 12px; }',
            '.rule-id { color: #666; font-family: monospace; width: 60px; }',
            '.rule-content { color: #333; }',
            '.rule-status { text-align: center; width: 50px; }',
            '.badge { padding: 1px 5px; border-radius: 2px; font-size: 10px; font-weight: bold; }',
            '.badge-pass { background: #d4edda; color: #155724; }',
            '.badge-fail { background: #f8d7da; color: #721c24; }',
            '.badge-review { background: #fff3cd; color: #856404; }',
            '.confidence { color: #888; font-size: 11px; text-align: right; width: 45px; }',
            '</style>',
            '</head><body>',
        ]

        # 批量摘要头部
        html_parts.append('<div class="batch-header">')
        html_parts.append('<div class="batch-title">【批量审核摘要】')
        html_parts.append(f'<span class="overall-badge" style="background:{overall_color};">{overall_status.upper()}</span>')
        html_parts.append('</div>')
        html_parts.append('<div class="batch-stats">')
        html_parts.append(f'总数: {total} | ')
        html_parts.append(f'<span style="color:#28a745;">PASS: {pass_count}</span> | ')
        html_parts.append(f'<span style="color:#856404;">REVIEW: {review_count}</span> | ')
        html_parts.append(f'<span style="color:#dc3545;">FAIL: {fail_count}</span>')
        html_parts.append('</div>')
        html_parts.append('</div>')

        # 每张图片的详细结果
        for i, result in enumerate(results, 1):
            status = result.get("status", "error")
            status_labels = {"pass": "PASS", "review": "REVIEW", "warning": "REVIEW", "fail": "FAIL", "error": "ERROR"}
            status_label = status_labels.get(status, "?")
            status_class = f"status-{status if status != 'warning' else 'review'}"
            file_name = result.get("file_name", "未知")

            html_parts.append('<div class="image-section">')
            html_parts.append('<div class="image-header">')
            html_parts.append(f'<span class="image-title">{i}. {file_name}</span>')
            html_parts.append(f'<span class="image-status {status_class}">{status_label}</span>')

            report = result.get("report", {})
            if report:
                score = report.get("score", 0)
                html_parts.append(f'<span class="image-score">分数: {score}</span>')
            html_parts.append('</div>')

            if result.get("status") == "error":
                html_parts.append(f'<div style="color:#666;">错误: {result.get("error", "未知错误")}</div>')
                html_parts.append('</div>')
                continue

            # 规则检查表格
            if report:
                rule_checks = report.get("rule_checks", [])
                if rule_checks:
                    # 按状态排序: fail > review > pass
                    status_order = {"fail": 0, "review": 1, "pass": 2}
                    sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

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

            html_parts.append('</div>')

        html_parts.append('</body></html>')
        return ''.join(html_parts)

    def _batch_to_expanded_text(self, data: dict) -> str:
        """将批量审核结果展开为详细纯文本"""
        results = data.get("results", [])
        summary = data.get("summary", {})

        total = summary.get("total", len(results))
        pass_count = summary.get("pass_count", 0)
        review_count = summary.get("review_count", summary.get("warning_count", 0))
        fail_count = summary.get("fail_count", 0)

        # 计算整体状态
        overall_status = data.get("status", "review")
        if fail_count > 0:
            overall_status = "fail"
        elif review_count > 0:
            overall_status = "review"
        else:
            overall_status = "pass"

        lines = [
            f"【批量审核摘要】",
            f"总数: {total} | PASS: {pass_count} | REVIEW: {review_count} | FAIL: {fail_count}",
            f"整体状态: {overall_status.upper()}",
            "",
            "【详细结果】",
            ""
        ]

        for i, result in enumerate(results, 1):
            status = result.get("status", "error")
            status_labels = {"pass": "PASS", "review": "REVIEW", "warning": "REVIEW", "fail": "FAIL", "error": "ERROR"}
            status_label = status_labels.get(status, "?")
            file_name = result.get("file_name", "未知")

            lines.append(f"--- 图片 {i}: {file_name} ---")
            lines.append(f"状态: [{status_label}]")

            if result.get("status") == "error":
                lines.append(f"错误: {result.get('error', '未知错误')}")
                lines.append("")
                continue

            report = result.get("report", {})
            if report:
                score = report.get("score", 0)
                lines.append(f"分数: {score}")

                rule_checks = report.get("rule_checks", [])
                if rule_checks:
                    status_order = {"fail": 0, "review": 1, "pass": 2}
                    sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status"), 3))

                    for check in sorted_checks:
                        rule_id = check.get("rule_id", "")
                        rule_content = check.get("rule_content", "") or rule_id
                        check_status = (check.get("status") or "review").lower()
                        if check_status == "warning":
                            check_status = "review"
                        if check_status not in ("pass", "review", "fail"):
                            check_status = "review"
                        confidence = check.get("confidence", 0)

                        badge_text = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}[check_status]
                        lines.append(f"[{badge_text}] {rule_id}: {rule_content} (置信度: {confidence:.0%})")

            lines.append("")

        return '\n'.join(lines)

    @Slot(str)
    def stop_streaming(self, status: str = ""):
        """
        停止流式输出，转换为HTML表格格式显示
        """
        super().stop_streaming(status)

        # 尝试解析并转换为HTML表格
        try:
            text = self._streaming_text.strip()
            data = self._parse_json(text)

            if data:
                self._raw_json = json.dumps(data, ensure_ascii=False, indent=2)
                html = self._audit_to_html(data)
                self.text_edit.setHtml(html)
                # 保留纯文本版本用于复制和导出
                self._streaming_text = self._audit_to_text(data)

                # 切换样式
                self.text_edit.setStyleSheet("""
                    TextEdit {
                        background-color: #ffffff;
                        border: 1px solid #e0e0e0;
                        border-radius: 4px;
                        padding: 8px;
                        font-family: 'Microsoft YaHei', 'Noto Sans CJK SC', sans-serif;
                        font-size: 13px;
                    }
                """)
        except Exception:
            # 解析失败，保持原样
            pass

    def _parse_json(self, text: str) -> Optional[dict]:
        """解析JSON文本"""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        first_brace = text.find('{')
        last_brace = text.rfind('}')
        if first_brace != -1 and last_brace != -1:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        return None

    def _audit_to_html(self, data: dict) -> str:
        """将审核结果JSON转换为HTML表格格式"""
        score = data.get("score", 0)
        status = data.get("status", "")
        summary = data.get("summary", "")
        rule_checks = data.get("rule_checks", [])

        # 状态样式 - 仅支持 pass/review/fail
        status_styles = {
            "pass": ("PASS", "#28a745", "#d4edda"),
            "review": ("REVIEW", "#856404", "#fff3cd"),
            "fail": ("FAIL", "#dc3545", "#f8d7da"),
        }
        # 默认为review
        normalized_status = (status or "review").lower()
        if normalized_status not in status_styles:
            normalized_status = "review"
        status_label, status_color, status_bg = status_styles[normalized_status]

        html_parts = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<meta charset="utf-8">',
            '<style>',
            'body { font-family: "Microsoft YaHei", sans-serif; font-size: 13px; margin: 0; padding: 0; width: 100%; }',
            '.header { display: flex; align-items: center; margin-bottom: 12px; padding-bottom: 10px; border-bottom: 1px solid #dee2e6; }',
            '.score-box { margin-right: 20px; }',
            '.score-value { font-size: 24px; font-weight: bold; color: #333; }',
            '.score-label { font-size: 12px; color: #666; }',
            '.status-badge { padding: 4px 12px; border-radius: 4px; font-weight: bold; font-size: 14px; }',
            '.summary-box { background: #f8f9fa; padding: 10px; border-radius: 6px; margin-bottom: 12px; }',
            '.summary-title { font-weight: bold; margin-bottom: 6px; color: #333; }',
            '.summary-text { color: #555; line-height: 1.5; }',
            'table { width: 100%; border-collapse: collapse; }',
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

        # 头部：分数和状态
        html_parts.append('<div class="header">')
        html_parts.append(f'<div class="score-box"><div class="score-value">{score}</div><div class="score-label">分数</div></div>')
        html_parts.append(f'<span class="status-badge" style="background:{status_bg};color:{status_color};">{status_label}</span>')
        html_parts.append('</div>')

        # 总体评价
        if summary:
            html_parts.append('<div class="summary-box">')
            html_parts.append('<div class="summary-title">总体评价</div>')
            html_parts.append(f'<div class="summary-text">{summary}</div>')
            html_parts.append('</div>')

        # 规则检查表格
        if rule_checks:
            # 按状态排序: fail > review > pass
            status_order = {"fail": 0, "review": 1, "pass": 2}
            sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status", "review"), 3))

            html_parts.append('<table>')
            html_parts.append('<tr><th>规则ID</th><th>规则内容</th><th>状态</th><th>置信度</th></tr>')

            for check in sorted_checks:
                rule_id = check.get("rule_id", "")
                rule_content = check.get("rule_content", "") or rule_id
                check_status = (check.get("status") or "review").lower()
                confidence = check.get("confidence", 0)

                # 规范化状态，仅支持 pass/review/fail
                if check_status not in ("pass", "review", "fail"):
                    check_status = "review"

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
        return ''.join(html_parts)

    def _audit_to_text(self, data: dict) -> str:
        """将审核结果转换为纯文本格式（用于复制和导出）"""
        lines = []

        score = data.get("score", 0)
        status = data.get("status", "")
        summary = data.get("summary", "")
        rule_checks = data.get("rule_checks", [])

        # 仅支持 pass/review/fail
        status_map = {"pass": "PASS", "review": "REVIEW", "fail": "FAIL"}
        normalized_status = (status or "review").lower()
        if normalized_status not in status_map:
            normalized_status = "review"
        status_label = status_map[normalized_status]

        lines.append(f"【审核结果】 分数: {score} | 状态: {status_label}")
        lines.append("")

        if summary:
            lines.append("【总体评价】")
            lines.append(f"  {summary}")
            lines.append("")

        if rule_checks:
            lines.append("【规则检查清单】")
            status_order = {"fail": 0, "review": 1, "pass": 2}
            sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status", "review"), 3))

            for check in sorted_checks:
                rule_id = check.get("rule_id", "")
                rule_content = check.get("rule_content", "") or rule_id
                check_status = (check.get("status") or "review").lower()
                confidence = check.get("confidence", 0)

                # 规范化状态
                if check_status not in ("pass", "review", "fail"):
                    check_status = "review"
                badge_text = {"pass": "PASS", "fail": "FAIL", "review": "REVIEW"}[check_status]

                lines.append(f"[{badge_text}] {rule_id}: {rule_content} (置信度: {confidence:.0%})")

        return '\n'.join(lines)

    def _audit_to_markdown(self, data: dict) -> str:
        """将审核结果JSON转换为Markdown格式 - 用于导出"""
        return self._audit_to_text(data)

    def get_parsed_json(self) -> Optional[dict]:
        """获取解析后的JSON对象"""
        if self._raw_json:
            try:
                return json.loads(self._raw_json)
            except:
                pass
        return None