"""主窗口模块 - 使用 FluentWindow"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon as FIF,
    InfoBar, InfoBarPosition, setTheme, Theme, setThemeColor
)

from gui.pages import SettingsPage, AuditPage, HistoryPage, RulesPage


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