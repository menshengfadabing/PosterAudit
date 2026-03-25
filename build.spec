# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置"""

import sys
from pathlib import Path

# 获取项目根目录
project_root = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        ('config', 'config'),
    ],
    hiddenimports=[
        # Qt
        'pyside6',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # Fluent Widgets
        'qfluentwidgets',
        'qframelesswindow',
        'pysidesix_frameless_window',
        # LLM
        'langchain_openai',
        'langchain_core',
        'openai',
        # Document parsing
        'pymupdf',
        'fitz',
        'pptx',
        'python_pptx',
        'docx',
        'python_docx',
        'openpyxl',
        'xlrd',
        'PIL',
        # Data
        'pydantic',
        'pydantic_settings',
        # Others
        'httpx',
        'dotenv',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'tests',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='BrandAudit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)