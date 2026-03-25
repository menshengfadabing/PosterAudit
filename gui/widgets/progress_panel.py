"""进度面板组件 - 显示任务执行进度和日志"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QTextEdit, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor, QFont


class ProgressPanel(QFrame):
    """进度面板 - 显示当前任务进度和详细日志"""

    # 信号
    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_expanded = False
        self._setup_ui()

    def _setup_ui(self):
        """初始化UI"""
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-top: 2px solid #3498db;
                border-radius: 0;
            }
            QLabel {
                color: #2c3e50;
            }
            QProgressBar {
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                text-align: center;
                background-color: #ecf0f1;
            }
            QProgressBar::chunk {
                background-color: #3498db;
                border-radius: 3px;
            }
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)

        # 顶部状态行
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # 任务状态标签
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        top_layout.addWidget(self.status_label, 1)

        # 展开/折叠按钮
        self.toggle_btn = QPushButton("展开日志")
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        self.toggle_btn.clicked.connect(self._toggle_expand)
        top_layout.addWidget(self.toggle_btn)

        # 取消按钮
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
        top_layout.addWidget(self.cancel_btn)

        layout.addLayout(top_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(24)
        layout.addWidget(self.progress_bar)

        # 详细信息标签
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(self.detail_label)

        # 日志区域（默认隐藏）
        self.log_text = QTextEdit()
        self.log_text.setVisible(False)
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet("""
            QTextEdit {
                font-size: 12px;
            }
        """)
        layout.addWidget(self.log_text)

        # 初始状态隐藏
        self.setVisible(False)

    def _toggle_expand(self):
        """切换展开/折叠状态"""
        self._is_expanded = not self._is_expanded
        self.log_text.setVisible(self._is_expanded)
        self.toggle_btn.setText("折叠日志" if self._is_expanded else "展开日志")

    def start_task(self, task_name: str, show_cancel: bool = True):
        """开始任务

        Args:
            task_name: 任务名称
            show_cancel: 是否显示取消按钮
        """
        self.status_label.setText(task_name)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.cancel_btn.setVisible(show_cancel)
        self.detail_label.setText("准备中...")
        self.log_text.clear()
        self.setVisible(True)

    def update_progress(self, percent: int, message: str = ""):
        """更新进度

        Args:
            percent: 进度百分比 (0-100)
            message: 进度消息
        """
        self.progress_bar.setValue(percent)
        if message:
            self.detail_label.setText(message)
            self._append_log(message)

    def set_indeterminate(self, message: str = ""):
        """设置为不确定进度模式"""
        self.progress_bar.setRange(0, 0)
        if message:
            self.detail_label.setText(message)

    def log(self, message: str, level: str = "INFO"):
        """添加日志

        Args:
            message: 日志消息
            level: 日志级别 (INFO, WARN, ERROR, SUCCESS)
        """
        self._append_log(f"[{level}] {message}")

    def _append_log(self, message: str):
        """追加日志"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        # 滚动到底部
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def finish_task(self, success: bool = True, message: str = ""):
        """完成任务

        Args:
            success: 是否成功
            message: 完成消息
        """
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.status_label.setText("完成")
            self.status_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #27ae60;")
            if message:
                self.detail_label.setText(message)
                self._append_log(f"[SUCCESS] {message}")
        else:
            self.status_label.setText("失败")
            self.status_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #e74c3c;")
            if message:
                self.detail_label.setText(message)
                self._append_log(f"[ERROR] {message}")

        self.cancel_btn.setVisible(False)

        # 3秒后自动隐藏
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, self.hide_panel)

    def hide_panel(self):
        """隐藏面板"""
        self.setVisible(False)
        self._is_expanded = False
        self.toggle_btn.setText("展开日志")
        self.log_text.setVisible(False)
        # 重置样式
        self.status_label.setStyleSheet("font-weight: bold; font-size: 14px;")