"""主窗口模块 - 使用 FluentWindow"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon as FIF,
    InfoBar, InfoBarPosition, setTheme, Theme, setThemeColor
)

from gui.pages import SettingsPage, AuditPage, HistoryPage, RulesPage
from gui.widgets import ProgressPanel


class MainWindow(FluentWindow):
    """主窗口 - 基于 FluentWindow"""

    def __init__(self):
        super().__init__()

        # 设置主题色 - 深蓝色
        setThemeColor('#1a5fb4')
        setTheme(Theme.LIGHT)

        self.setWindowTitle("品牌合规性智能审核平台")
        self.setMinimumSize(1400, 900)
        self.resize(1600, 1000)

        # 创建子页面
        self._create_pages()

        # 初始化导航
        self._init_navigation()

        # 连接信号
        self._connect_signals()

        # 创建进度面板
        self._create_progress_panel()

    def _create_pages(self):
        """创建子页面"""
        self.settingsPage = SettingsPage(self)
        self.rulesPage = RulesPage(self)
        self.auditPage = AuditPage(self)
        self.historyPage = HistoryPage(self)

    def _init_navigation(self):
        """初始化导航栏"""
        # 添加导航项 - 按功能分组
        self.addSubInterface(
            self.settingsPage,
            FIF.SETTING,
            "API设置",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.rulesPage,
            FIF.BOOK_SHELF,
            "规范管理",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.auditPage,
            FIF.DICTIONARY,
            "设计审核",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.historyPage,
            FIF.HISTORY,
            "审核历史",
            NavigationItemPosition.TOP
        )

        # 设置默认页面
        self.switchTo(self.auditPage)

    def _connect_signals(self):
        """连接信号"""
        # 连接审核页面的进度信号
        self.auditPage.task_started.connect(self._on_task_started)
        self.auditPage.progress_updated.connect(self._on_progress_updated)
        self.auditPage.task_finished.connect(self._on_task_finished)

        # 连接规范页面的进度信号
        self.rulesPage.task_started.connect(self._on_task_started)
        self.rulesPage.progress_updated.connect(self._on_progress_updated)
        self.rulesPage.task_finished.connect(self._on_task_finished)

    def _create_progress_panel(self):
        """创建进度面板"""
        self.progressPanel = ProgressPanel(self)
        self.progressPanel.hide()

    def _on_task_started(self, task_name: str):
        """任务开始"""
        self.progressPanel.show()
        self.progressPanel.start_task(task_name)

    def _on_progress_updated(self, percent: int, message: str, log_message: str):
        """进度更新"""
        self.progressPanel.update_progress(percent, message, log_message)

    def _on_task_finished(self, success: bool, message: str):
        """任务完成"""
        self.progressPanel.finish_task(success, message)

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