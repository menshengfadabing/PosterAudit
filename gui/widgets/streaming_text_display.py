"""流式文本显示组件 - 用于实时显示LLM输出"""

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtGui import QTextCursor, QFont

from qfluentwidgets import (
    TextEdit, PushButton, CaptionLabel, FluentIcon as FIF,
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
    """

    # 文本更新信号
    text_appended = Signal(str)
    cleared = Signal()

    def __init__(self, parent=None, title: str = "AI 输出", max_height: int = 300):
        super().__init__(parent)
        self._title = title
        self._max_height = max_height
        self._is_streaming = False
        self._streaming_text = ""  # 累积的流式文本

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

        # 默认隐藏
        self.setVisible(False)

    @Slot(str)
    def append_text(self, text: str):
        """
        追加文本到显示区域

        Args:
            text: 要追加的文本
        """
        if not self.isVisible():
            self.setVisible(True)

        # 累积文本
        self._streaming_text += text

        # 移动光标到末尾并插入文本
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self.text_edit.setTextCursor(cursor)

        # 滚动到底部
        self.text_edit.ensureCursorVisible()

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

        if text and not self.isVisible():
            self.setVisible(True)

    @Slot()
    def clear(self):
        """清空文本"""
        self._streaming_text = ""
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
        self.setVisible(True)
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

    def __init__(self, parent=None, title: str = "AI 输出 (JSON)", max_height: int = 300):
        super().__init__(parent, title, max_height)

    @Slot(str)
    def stop_streaming(self, status: str = ""):
        """
        停止流式输出，尝试格式化JSON
        """
        super().stop_streaming(status)

        # 尝试格式化JSON
        try:
            import json
            import re

            text = self._streaming_text.strip()

            # 尝试直接解析
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 尝试提取JSON块
                json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
                if json_match:
                    data = json.loads(json_match.group(1))
                else:
                    # 尝试找到第一个 { 和最后一个 }
                    first_brace = text.find('{')
                    last_brace = text.rfind('}')
                    if first_brace != -1 and last_brace != -1:
                        data = json.loads(text[first_brace:last_brace + 1])
                    else:
                        return  # 无法解析，保持原样

            # 格式化显示
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
            self.text_edit.setPlainText(formatted)
            self._streaming_text = formatted

        except Exception:
            # 解析失败，保持原样
            pass