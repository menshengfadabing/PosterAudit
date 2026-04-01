"""品牌合规审核平台 - 程序入口"""

import sys
import logging
from pathlib import Path


def setup_logging():
    """配置日志"""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )
    # 降低第三方库的日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)


def main():
    """主函数"""
    import os

    # 禁用 QFluentWidgets 的宣传信息
    os.environ['QFLUENTWidgets_DISABLE_TIPS'] = '1'

    # 强制加载 .env 文件（覆盖系统环境变量）
    app_dir = Path(__file__).parent
    env_file = app_dir / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file, override=True)  # override=True 确保覆盖系统环境变量

    # 配置日志
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("品牌合规审核平台启动...")

    # 设置工作目录
    if getattr(sys, 'frozen', False):
        # 打包后的路径
        app_dir = Path(sys.executable).parent
        os.chdir(app_dir)

    # 确保数据目录存在
    from src.utils.config import ensure_data_dirs
    ensure_data_dirs()

    # 导入Qt相关模块
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # 启用高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 创建应用
    app = QApplication(sys.argv)

    # 设置 Fluent 主题
    from qfluentwidgets import setThemeColor, setTheme, Theme
    setThemeColor('#1a5fb4')  # 深蓝色
    setTheme(Theme.LIGHT)

    # 创建主窗口
    from gui import MainWindow
    window = MainWindow()
    window.show()

    # 检查配置
    from src.utils.config import settings
    if not settings.openai_api_key:
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.warning(
            title="提示",
            content="请在设置页面配置API Key",
            position=InfoBarPosition.TOP,
            duration=5000,
            parent=window
        )

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()