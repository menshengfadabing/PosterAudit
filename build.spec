# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - 跨平台支持"""

import sys
from pathlib import Path

# 获取项目根目录
project_root = Path(SPECPATH)

# 收集所有需要的数据文件
datas = [
    ('config', 'config'),
]

# 检查是否有额外的数据目录
data_dir = project_root / 'data'
if data_dir.exists():
    datas.append(('data', 'data'))

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # Qt 核心
        'pyside6',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'PySide6.QtNetwork',
        # Fluent Widgets
        'qfluentwidgets',
        'qfluentwidgets.common',
        'qfluentwidgets.components',
        'qfluentwidgets.components.widgets',
        'qfluentwidgets.window',
        'qframelesswindow',
        'pysidesix_frameless_window',
        # LLM
        'langchain_openai',
        'langchain_core',
        'langchain_core.runnables',
        'langchain_core.messages',
        'langchain_core.prompts',
        'langchain_core.output_parsers',
        'openai',
        'httpx',
        'httpcore',
        'h11',
        # Document parsing
        'pymupdf',
        'fitz',
        'fitz._fitz',
        'pptx',
        'python_pptx',
        'docx',
        'python_docx',
        'openpyxl',
        'xlrd',
        'PIL',
        'PIL._imaging',
        # Data
        'pydantic',
        'pydantic_settings',
        'pydantic_core',
        'annotated_types',
        # Utils
        'dotenv',
        'typing_extensions',
        'distro',
        'jiter',
        'sniffio',
        'anyio',
        'tenacity',
        'regex',
        # JSON
        'json',
        'json.decoder',
        'json.encoder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'tests',
        'pytest',
        'IPython',
        'jupyter',
        'notebook',
        'sphinx',
        'docutils',
    ],
    noarchive=False,
    optimize=2,
)

pyz = PYZ(a.pure, a.zipped_data)

# 根据平台选择打包方式
if sys.platform == 'darwin':
    # macOS: 生成 .app 包
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='品牌合规审核平台',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch='arm64',  # GitHub Actions 使用 Apple Silicon 运行器
        codesign_identity=None,
        entitlements_file=None,
        icon='config/icon.icns' if (project_root / 'config' / 'icon.icns').exists() else None,
    )
else:
    # Windows/Linux: 生成单文件可执行程序
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='品牌合规审核平台' if sys.platform == 'win32' else 'BrandAudit',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='config/icon.ico' if (project_root / 'config' / 'icon.ico').exists() else None,
    )