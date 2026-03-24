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

    # 设置全局字体
    font = app.font()
    font.setFamily("Microsoft YaHei")
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