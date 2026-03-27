"""进度面板组件 - 显示任务执行进度和终端日志"""

import datetime
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QTextEdit, QPushButton, QFrame
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont


class QtLogHandler(logging.Handler):
    """自定义日志处理器，将日志发送到Qt信号"""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        try:
            msg = self.format(record)
            self.callback(record.levelno, msg)
        except Exception:
            pass


class ProgressPanel(QFrame):
    """进度面板 - 显示当前任务进度和终端日志"""

    cancel_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_expanded = False
        self._log_handler = None
        self._setup_ui()
        self._setup_log_handler()

    def _setup_ui(self):
        """初始化UI"""
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border-top: 2px solid #3498db;
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
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: none;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(8)

        # 顶部状态行
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("font-weight: bold;")
        top_layout.addWidget(self.status_label, 1)

        self.toggle_btn = QPushButton("展开日志")
        self.toggle_btn.clicked.connect(self._toggle_expand)
        top_layout.addWidget(self.toggle_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setStyleSheet("background-color: #1a5fb4; color: white;")
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self.cancel_clicked.emit)
        top_layout.addWidget(self.cancel_btn)

        layout.addLayout(top_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 详细信息标签
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color: #7f8c8d;")
        layout.addWidget(self.detail_label)

        # 终端日志区域（默认隐藏）
        self.log_text = QTextEdit()
        self.log_text.setVisible(False)
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)

        self.setVisible(False)

    def _setup_log_handler(self):
        """设置日志处理器"""
        self._log_handler = QtLogHandler(self._append_log)
        self._log_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        ))

    def _toggle_expand(self):
        """切换展开/折叠"""
        self._is_expanded = not self._is_expanded
        self.log_text.setVisible(self._is_expanded)
        self.toggle_btn.setText("折叠日志" if self._is_expanded else "展开日志")

    def start_task(self, task_name: str, show_cancel: bool = True):
        """开始任务"""
        self.status_label.setText(task_name)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.cancel_btn.setVisible(show_cancel)
        self.detail_label.setText("准备中...")
        self.log_text.clear()
        self.setVisible(True)

        # 添加日志处理器到根logger
        root_logger = logging.getLogger()
        root_logger.addHandler(self._log_handler)

    def update_progress(self, percent: int, message: str = ""):
        """更新进度"""
        self.progress_bar.setValue(percent)
        if message:
            self.detail_label.setText(message)

    def set_indeterminate(self, message: str = ""):
        """设置不确定进度"""
        self.progress_bar.setRange(0, 0)
        if message:
            self.detail_label.setText(message)

    def log(self, message: str, level: str = "INFO"):
        """手动添加日志"""
        level_no = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "SUCCESS": logging.INFO
        }.get(level, logging.INFO)
        self._append_log(level_no, f"[{level}] {message}")

    @Slot(int, str)
    def _append_log(self, level: int, message: str):
        """追加日志到文本框"""
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # 根据日志级别设置颜色
        fmt = QTextCharFormat()
        if level >= logging.ERROR:
            fmt.setForeground(QColor("#f44747"))  # 红色
        elif level >= logging.WARNING:
            fmt.setForeground(QColor("#dcdcaa"))  # 黄色
        elif level >= logging.INFO:
            fmt.setForeground(QColor("#d4d4d4"))  # 白色
        else:
            fmt.setForeground(QColor("#6a9955"))  # 绿色

        cursor.insertText(message + "\n", fmt)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def finish_task(self, success: bool = True, message: str = ""):
        """完成任务"""
        # 移除日志处理器
        if self._log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self._log_handler)

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.status_label.setText("完成")
            self.status_label.setStyleSheet("font-weight: bold; color: #27ae60;")
            if message:
                self.detail_label.setText(message)
                self._append_log(logging.INFO, f"[SUCCESS] {message}")
        else:
            self.status_label.setText("失败")
            self.status_label.setStyleSheet("font-weight: bold; color: #e74c3c;")
            if message:
                self.detail_label.setText(message)
                self._append_log(logging.ERROR, f"[ERROR] {message}")

        self.cancel_btn.setVisible(False)

        from PySide6.QtCore import QTimer
        QTimer.singleShot(5000, self.hide_panel)

    def hide_panel(self):
        """隐藏面板"""
        # 确保移除日志处理器
        if self._log_handler:
            root_logger = logging.getLogger()
            try:
                root_logger.removeHandler(self._log_handler)
            except:
                pass

        self.setVisible(False)
        self._is_expanded = False
        self.toggle_btn.setText("展开日志")
        self.log_text.setVisible(False)
        self.status_label.setStyleSheet("font-weight: bold;")