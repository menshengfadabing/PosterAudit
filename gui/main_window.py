"""主窗口模块"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QStackedWidget, QLabel, QFrame, QStatusBar, QMessageBox, QListWidgetItem,
    QSizePolicy
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont

from gui.pages import SettingsPage, AuditPage, HistoryPage
from gui.widgets import ProgressPanel


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("品牌合规性智能审核平台")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 内容区域（侧边栏 + 页面）
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 侧边栏
        sidebar = self._create_sidebar()
        content_layout.addWidget(sidebar)

        # 内容区
        content_area = self._create_content_area()
        content_layout.addWidget(content_area, 1)

        main_layout.addLayout(content_layout, 1)

        # 进度面板
        self.progress_panel = ProgressPanel()
        main_layout.addWidget(self.progress_panel)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # 应用全局样式
        self._apply_global_style()

    def _apply_global_style(self):
        """应用全局样式"""
        self.setStyleSheet("""
            QWidget {
                font-size: 15px;
            }
            QLabel {
                font-size: 15px;
            }
            QPushButton {
                font-size: 15px;
                padding: 8px 16px;
            }
            QLineEdit {
                font-size: 15px;
                padding: 8px;
            }
            QTextEdit {
                font-size: 15px;
            }
            QComboBox {
                font-size: 15px;
                padding: 8px;
            }
            QTableWidget {
                font-size: 14px;
            }
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
            }
        """)

    def _create_sidebar(self) -> QWidget:
        """创建侧边栏"""
        sidebar = QFrame()
        sidebar.setMinimumWidth(220)
        sidebar.setMaximumWidth(280)
        sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border: none;
            }
            QListWidget {
                background-color: #2c3e50;
                border: none;
                color: #ecf0f1;
                font-size: 17px;
            }
            QListWidget::item {
                padding: 20px 25px;
                border: none;
            }
            QListWidget::item:hover {
                background-color: #34495e;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title_label = QLabel("品牌合规审核")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #ecf0f1;
                font-size: 22px;
                font-weight: bold;
                padding: 25px;
                background-color: #1a252f;
            }
        """)
        layout.addWidget(title_label)

        # 导航列表
        self.nav_list = QListWidget()
        self.nav_list.setFrameShape(QFrame.Shape.NoFrame)
        self.nav_list.setSpacing(5)

        nav_items = [
            ("⚙️ 系统设置", "settings"),
            ("🎨 设计审核", "audit"),
            ("📊 报告历史", "history"),
        ]

        for text, key in nav_items:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setSizeHint(QSize(0, 60))  # 更高的导航项
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(0)
        layout.addWidget(self.nav_list)

        # 版本信息
        version_label = QLabel("v1.0.0")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 13px;
                padding: 15px;
            }
        """)
        layout.addWidget(version_label)

        return sidebar

    def _create_content_area(self) -> QWidget:
        """创建内容区"""
        content = QFrame()
        content.setStyleSheet("background-color: #f5f6fa;")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 30, 30, 30)

        # 堆栈窗口
        self.stack = QStackedWidget()

        # 创建各页面
        self.pages = {
            'settings': SettingsPage(),
            'audit': AuditPage(),
            'history': HistoryPage(),
        }

        for page in self.pages.values():
            self.stack.addWidget(page)

        layout.addWidget(self.stack)

        return content

    def _connect_signals(self):
        """连接信号"""
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)

        # 连接审核页面的进度信号
        audit_page = self.pages['audit']
        audit_page.task_started.connect(self._on_task_started)
        audit_page.progress_updated.connect(self._on_progress_updated)
        audit_page.task_finished.connect(self._on_task_finished)

        # 连接设置页面的进度信号
        settings_page = self.pages['settings']
        settings_page.task_started.connect(self._on_task_started)
        settings_page.progress_updated.connect(self._on_progress_updated)
        settings_page.task_finished.connect(self._on_task_finished)

    def _on_task_started(self, task_name: str):
        """任务开始"""
        self.progress_panel.start_task(task_name)

    def _on_progress_updated(self, percent: int, message: str, log_message: str):
        """进度更新"""
        if percent < 0:
            self.progress_panel.set_indeterminate(message)
        else:
            self.progress_panel.update_progress(percent, message)
        if log_message:
            self.progress_panel.log(log_message)

    def _on_task_finished(self, success: bool, message: str):
        """任务完成"""
        self.progress_panel.finish_task(success, message)

    def _on_nav_changed(self, row: int):
        """导航项改变"""
        item = self.nav_list.item(row)
        if item:
            key = item.data(Qt.ItemDataRole.UserRole)
            if key in self.pages:
                self.stack.setCurrentWidget(self.pages[key])

                if key == 'history':
                    self.pages['history'].refresh()

    def show_status(self, message: str, timeout: int = 3000):
        """显示状态消息"""
        self.status_bar.showMessage(message, timeout)

    def closeEvent(self, event):
        """关闭事件"""
        reply = QMessageBox.question(
            self,
            "确认退出",
            "确定要退出程序吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            event.accept()
        else:
            event.ignore()