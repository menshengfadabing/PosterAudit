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

    输出JSON，完成后自动转换为可读的Markdown格式审核报告
    """

    def __init__(self, parent=None, max_height: int = 400, show_export: bool = False):
        super().__init__(parent, "AI 审核输出", max_height, show_export)
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
                markdown = self._audit_to_markdown(data)
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

    def _audit_to_markdown(self, data: dict) -> str:
        """将审核结果JSON转换为Markdown格式 - 同步导出报告格式"""
        lines = []

        # 评分和状态
        score = data.get("score", 0)
        status = data.get("status", "unknown")

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
        summary = data.get("summary", "")
        if summary:
            lines.append("【总体评价】")
            lines.append(f"  {summary}")
            lines.append("")

        # 规则检查清单 - 使用导出报告格式
        rule_checks = data.get("rule_checks", [])
        if rule_checks:
            lines.append("【规则检查清单】")
            lines.append("")

            # 按状态分组排序: fail > review > pass
            status_order = {"fail": 0, "review": 1, "pass": 2}
            sorted_checks = sorted(rule_checks, key=lambda x: status_order.get(x.get("status", "pass"), 3))

            for check in sorted_checks:
                rule_id = check.get("rule_id", "")
                rule_content = check.get("rule_content", "") or rule_id
                check_status = check.get("status", "pass")
                confidence = check.get("confidence", 0)
                reference = check.get("reference", "")

                # 状态图标
                if check_status == "pass":
                    status_label = "PASS"
                elif check_status == "fail":
                    status_label = "FAIL"
                else:
                    status_label = "REVIEW"

                # 导出报告格式: [状态] Rule_ID : 规则内容 -->> 状态 >> 参考文档，置信度：0.XX；
                lines.append(f"[{status_label}] {rule_id} : {rule_content} -->> {status_label} >> {reference}，置信度：{confidence:.2f}；")

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