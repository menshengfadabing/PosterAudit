"""品牌合规审核平台 - 程序入口"""

import sys
from pathlib import Path


def main():
    """主函数"""
    # 设置工作目录
    import os
    if getattr(sys, 'frozen', False):
        # 打包后的路径
        app_dir = Path(sys.executable).parent
        os.chdir(app_dir)
    else:
        # 开发环境
        app_dir = Path(__file__).parent

    # 导入Qt相关模块
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 创建应用
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    # 设置全局字体 - 跨平台中文字体支持
    font = app.font()
    from PySide6.QtGui import QFontDatabase
    families = QFontDatabase.families()

    # 按优先级选择中文字体
    chinese_fonts = [
        "Noto Sans CJK SC",      # Linux 常用
        "WenQuanYi Micro Hei",  # Linux 常用
        "Source Han Sans SC",    # 思源黑体
        "Microsoft YaHei",       # Windows
        "SimHei",                # Windows 黑体
        "PingFang SC",           # macOS
        "Hiragino Sans GB",      # macOS
    ]

    for chinese_font in chinese_fonts:
        if chinese_font in families:
            font.setFamily(chinese_font)
            break
    else:
        # 如果没有中文字体，使用系统默认字体
        font.setFamily("Sans Serif")

    app.setFont(font)

    # 创建主窗口
    from gui import MainWindow
    window = MainWindow()
    window.show()

    # 检查配置
    from src.utils.config import settings
    if not settings.openai_api_key:
        window.show_status("请在设置页面配置API Key", 5000)

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()