"""主窗口模块 - 使用 FluentWindow 实现现代化界面"""

import sys
from PySide6.QtCore import Qt, QRectF, QPoint
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QRegion, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QApplication

from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, FluentIcon as FIF,
    InfoBar, InfoBarPosition, setTheme, Theme, setThemeColor,
    isDarkTheme
)

from gui.pages import SettingsPage, AuditPage, HistoryPage, RulesPage
from gui.utils.responsive import responsive


class MainWindow(FluentWindow):
    """主窗口 - 基于 FluentWindow 实现现代 Fluent Design"""

    # 窗口圆角半径
    BORDER_RADIUS = 10

    def __init__(self):
        super().__init__()

        # 现代主题色 - Indigo (低饱和、高明度)
        setThemeColor('#6366F1')
        setTheme(Theme.LIGHT)

        # 启用导航栏亚克力效果
        self.navigationInterface.setAcrylicEnabled(True)

        self.setWindowTitle("品牌合规性智能审核平台")
        self.setMinimumSize(1200, 800)
        self.resize(1600, 1000)

        # 创建子页面
        self._create_pages()

        # 初始化导航
        self._init_navigation()

        # 应用初始样式
        self._apply_responsive_style()

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

    def _apply_responsive_style(self):
        """应用响应式样式 - 字体固定大小，布局等比例缩放"""
        scale = responsive.scale
        # 固定字体大小，不再随 scale 变化
        base_font = 16  # 固定基础字体大小
        radius = int(self.BORDER_RADIUS * scale)

        # 设置全局字体
        font = QFont()
        font.setPointSize(base_font)
        QApplication.instance().setFont(font)

        # 设置全局样式表 - 固定字体大小，响应式间距和圆角
        # 注意：保留 StackedWidget 的圆角样式
        style = f"""
            QWidget {{
                font-size: {base_font}px;
            }}
            TitleLabel {{
                font-size: 24px;
                font-weight: bold;
            }}
            SubtitleLabel {{
                font-size: 20px;
                font-weight: 500;
            }}
            StrongBodyLabel {{
                font-size: 18px;
                font-weight: 600;
            }}
            BodyLabel {{
                font-size: {base_font}px;
            }}
            CaptionLabel {{
                font-size: 14px;
                color: #666;
            }}
            PrimaryPushButton {{
                font-size: {base_font}px;
                padding: {int(10 * scale)}px {int(24 * scale)}px;
                border-radius: {int(6 * scale)}px;
            }}
            PushButton {{
                font-size: {base_font}px;
                padding: {int(8 * scale)}px {int(18 * scale)}px;
                border-radius: {int(6 * scale)}px;
            }}
            ComboBox {{
                font-size: {base_font}px;
                padding: {int(8 * scale)}px;
                border-radius: {int(5 * scale)}px;
            }}
            LineEdit, TextEdit {{
                font-size: {base_font}px;
                padding: {int(8 * scale)}px;
                border-radius: {int(5 * scale)}px;
            }}
            TableWidget {{
                font-size: {base_font}px;
                border-radius: {int(8 * scale)}px;
            }}
            CardWidget {{
                border-radius: {int(12 * scale)}px;
            }}
            /* StackedWidget 圆角 - 倒数第二层 */
            StackedWidget {{
                border: 1px solid rgba(0, 0, 0, 0.068);
                border-right: none;
                border-bottom: none;
                border-top-left-radius: {radius}px;
                background-color: rgba(255, 255, 255, 0.5);
            }}
        """
        self.setStyleSheet(style)

    def showEvent(self, e):
        """窗口显示时应用圆角"""
        super().showEvent(e)
        # 在 Linux 上需要延迟设置遮罩
        if sys.platform == 'linux':
            from PySide6.QtCore import QTimer
            QTimer.singleShot(100, self._apply_linux_rounded_corners)

    def _apply_linux_rounded_corners(self):
        """在 Linux 上应用圆角"""
        if self.isMaximized():
            self.clearMask()
            return

        # 创建圆角遮罩
        path = QPainterPath()
        rect = QRectF(self.rect())
        path.addRoundedRect(rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

        # 转换为 QRegion
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)

    def resizeEvent(self, e):
        """窗口大小变化时更新响应式布局"""
        super().resizeEvent(e)
        # 更新缩放因子
        old_scale = responsive.scale
        responsive.update_scale(self.width(), self.height())

        # 如果缩放变化超过阈值，更新样式
        if abs(responsive.scale - old_scale) > 0.02:
            self._apply_responsive_style()

        # Linux 上更新圆角遮罩
        if sys.platform == 'linux':
            self._apply_linux_rounded_corners()

    def changeEvent(self, e):
        """窗口状态变化事件"""
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange:
            # Linux 上窗口最大化/还原时更新遮罩
            if sys.platform == 'linux':
                if self.isMaximized():
                    self.clearMask()
                else:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(50, self._apply_linux_rounded_corners)

    def paintEvent(self, e):
        """绘制窗口背景和圆角边框"""
        # 在 Linux 上绘制圆角背景
        if sys.platform == 'linux' and not self.isMaximized():
            painter = QPainter(self)
            painter.setRenderHints(QPainter.Antialiasing)

            # 绘制背景
            rect = QRectF(self.rect())
            path = QPainterPath()
            path.addRoundedRect(rect, self.BORDER_RADIUS, self.BORDER_RADIUS)

            # 背景
            if isDarkTheme():
                bgColor = QColor(32, 32, 32)
                borderColor = QColor(255, 255, 255, 30)
            else:
                bgColor = QColor(240, 244, 249)
                borderColor = QColor(0, 0, 0, 30)

            painter.setPen(Qt.NoPen)
            painter.setBrush(bgColor)
            painter.drawPath(path)

            # 绘制边框
            painter.setPen(QPen(borderColor, 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        super().paintEvent(e)

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