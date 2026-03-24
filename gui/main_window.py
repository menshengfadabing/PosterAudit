"""主窗口模块"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QStackedWidget, QLabel, QFrame, QStatusBar, QMessageBox, QListWidgetItem
)
from PySide6.QtCore import Qt

from gui.pages import SettingsPage, AuditPage, HistoryPage


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("品牌合规性智能审核平台")
        self.setMinimumSize(1200, 800)

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        """初始化UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 侧边栏
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar)

        # 内容区
        content_area = self._create_content_area()
        main_layout.addWidget(content_area, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

    def _create_sidebar(self) -> QWidget:
        """创建侧边栏"""
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border: none;
            }
            QListWidget {
                background-color: #2c3e50;
                border: none;
                color: #ecf0f1;
                font-size: 14px;
            }
            QListWidget::item {
                padding: 15px 20px;
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
                font-size: 18px;
                font-weight: bold;
                padding: 20px;
                background-color: #1a252f;
            }
        """)
        layout.addWidget(title_label)

        # 导航列表
        self.nav_list = QListWidget()
        self.nav_list.setFrameShape(QFrame.Shape.NoFrame)

        nav_items = [
            ("设置", "settings"),
            ("设计审核", "audit"),
            ("报告历史", "history"),
        ]

        for text, key in nav_items:
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.nav_list.addItem(item)

        self.nav_list.setCurrentRow(0)
        layout.addWidget(self.nav_list)

        # 版本信息
        version_label = QLabel("v1.0.0")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("""
            QLabel {
                color: #7f8c8d;
                font-size: 11px;
                padding: 10px;
            }
        """)
        layout.addWidget(version_label)

        return sidebar

    def _create_content_area(self) -> QWidget:
        """创建内容区"""
        content = QFrame()
        content.setStyleSheet("background-color: #f5f6fa;")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)

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