"""响应式布局工具"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication


class ResponsiveLayout(QObject):
    """响应式布局管理器"""

    # 基准窗口尺寸
    BASE_WIDTH = 1600
    BASE_HEIGHT = 1000

    # 基础字体大小（调大）
    BASE_FONT_SIZE = 16

    # 缩放因子变化信号
    scale_changed = Signal(float)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        super().__init__()
        self._initialized = True
        self._scale = 1.0

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def update_scale(self, width: int, height: int):
        """更新缩放因子"""
        # 取宽高缩放的平均值
        scale_x = width / self.BASE_WIDTH
        scale_y = height / self.BASE_HEIGHT
        new_scale = (scale_x + scale_y) / 2

        # 限制缩放范围 - 提高最小值让小窗口字体也够大
        new_scale = max(0.85, min(1.5, new_scale))

        if abs(new_scale - self._scale) > 0.01:
            self._scale = new_scale
            self.scale_changed.emit(self._scale)

    @property
    def scale(self) -> float:
        return self._scale

    def scaled(self, value: int) -> int:
        """返回缩放后的整数值"""
        return max(1, int(value * self._scale))

    def font_size(self, base_size: int) -> int:
        """返回缩放后的字体大小 - 设置最小值"""
        return max(12, int(base_size * self._scale))

    def spacing(self) -> int:
        """返回缩放后的标准间距"""
        return self.scaled(16)

    def margin(self) -> int:
        """返回缩放后的标准边距"""
        return self.scaled(20)

    def card_radius(self) -> int:
        """返回缩放后的卡片圆角"""
        return self.scaled(12)

    def button_height(self) -> int:
        """返回缩放后的按钮高度"""
        return self.scaled(36)


# 全局实例
responsive = ResponsiveLayout.instance()