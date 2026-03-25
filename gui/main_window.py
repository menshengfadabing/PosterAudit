"""主窗口模块 - 使用 FluentWindow"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon as FIF,
    InfoBar, InfoBarPosition, setTheme, Theme
)

from gui.pages import SettingsPage, AuditPage, HistoryPage
from gui.widgets import ProgressPanel


class MainWindow(FluentWindow):
    """主窗口 - 基于 FluentWindow"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("品牌合规性智能审核平台")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)

        # 创建子页面
        self._create_pages()

        # 初始化导航
        self._init_navigation()

        # 连接信号
        self._connect_signals()

    def _create_pages(self):
        """创建子页面"""
        self.settingsPage = SettingsPage(self)
        self.auditPage = AuditPage(self)
        self.historyPage = HistoryPage(self)

    def _init_navigation(self):
        """初始化导航栏"""
        # 添加导航项
        self.addSubInterface(
            self.settingsPage,
            FIF.SETTING,
            "系统设置",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.auditPage,
            FIF.PALETTE,
            "设计审核",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.historyPage,
            FIF.HISTORY,
            "报告历史",
            NavigationItemPosition.BOTTOM
        )

        # 设置默认页面
        self.switchTo(self.auditPage)

    def _connect_signals(self):
        """连接信号"""
        # 连接审核页面的进度信号
        self.auditPage.task_started.connect(self._on_task_started)
        self.auditPage.progress_updated.connect(self._on_progress_updated)
        self.auditPage.task_finished.connect(self._on_task_finished)

        # 连接设置页面的进度信号
        self.settingsPage.task_started.connect(self._on_task_started)
        self.settingsPage.progress_updated.connect(self._on_progress_updated)
        self.settingsPage.task_finished.connect(self._on_task_finished)

    def _on_task_started(self, task_name: str):
        """任务开始"""
        # 在底部显示进度提示
        pass

    def _on_progress_updated(self, percent: int, message: str, log_message: str):
        """进度更新"""
        # 可以在这里更新状态栏或其他UI
        pass

    def _on_task_finished(self, success: bool, message: str):
        """任务完成"""
        if success:
            InfoBar.success(
                title="完成",
                content=message,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )
        else:
            InfoBar.error(
                title="失败",
                content=message,
                position=InfoBarPosition.TOP,
                duration=5000,
                parent=self
            )

    def show_status(self, message: str, timeout: int = 3000):
        """显示状态消息"""
        InfoBar.info(
            title="提示",
            content=message,
            position=InfoBarPosition.TOP,
            duration=timeout,
            parent=self
        )

    def closeEvent(self, event):
        """关闭事件"""
        from qfluentwidgets import MessageBox

        box = MessageBox(
            "确认退出",
            "确定要退出程序吗？",
            self
        )
        box.yesButton.setText("确定")
        box.cancelButton.setText("取消")

        if box.exec():
            event.accept()
        else:
            event.ignore()