@echo off
chcp 65001 >nul
REM ========================================
REM 品牌合规审核平台 - Windows 打包脚本
REM ========================================

echo.
echo ========================================
echo   品牌合规审核平台 - Windows 打包工具
echo ========================================
echo.

REM 检查 Python 环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.10+
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 检查 pip
pip --version >nul 2>&1
if errorlevel 1 (
    echo [错误] pip 未正确安装
    pause
    exit /b 1
)

echo [1/5] 安装依赖包...
pip install pyinstaller -q
pip install -r requirements.txt -q 2>nul || pip install pyside6 pyside6-fluent-widgets langchain-openai pymupdf python-pptx python-docx openpyxl xlrd pillow pydantic pydantic-settings httpx -q

echo [2/5] 创建必要目录...
if not exist "data" mkdir data
if not exist "data\rules" mkdir data\rules
if not exist "data\audit_history" mkdir data\audit_history
if not exist "data\exports" mkdir data\exports
if not exist "data\uploads" mkdir data\uploads

echo [3/5] 清理旧的打包文件...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

echo [4/5] 开始打包 (这可能需要几分钟)...
pyinstaller build.spec --noconfirm --clean

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请检查错误信息
    pause
    exit /b 1
)

echo [5/5] 创建发布包...
cd dist
if exist "品牌合规审核平台.exe" (
    echo 正在创建发布目录...
    if not exist "品牌合规审核平台" mkdir "品牌合规审核平台"
    move "品牌合规审核平台.exe" "品牌合规审核平台\" >nul
    xcopy /e /i /y "..\data" "品牌合规审核平台\data" >nul 2>&1
    xcopy /e /i /y "..\config" "品牌合规审核平台\config" >nul 2>&1

    echo 正在创建启动脚本...
    echo @echo off > "品牌合规审核平台\启动程序.bat"
    echo chcp 65001 ^>nul >> "品牌合规审核平台\启动程序.bat"
    echo cd /d "%%~dp0" >> "品牌合规审核平台\启动程序.bat"
    echo start "" "品牌合规审核平台.exe" >> "品牌合规审核平台\启动程序.bat"

    echo 正在创建使用说明...
    echo 品牌合规审核平台 > "品牌合规审核平台\使用说明.txt"
    echo ================================ >> "品牌合规审核平台\使用说明.txt"
    echo. >> "品牌合规审核平台\使用说明.txt"
    echo 使用方法: >> "品牌合规审核平台\使用说明.txt"
    echo 1. 双击 "启动程序.bat" 或直接运行 "品牌合规审核平台.exe" >> "品牌合规审核平台\使用说明.txt"
    echo 2. 首次使用请先在 "API设置" 中配置 API Key >> "品牌合规审核平台\使用说明.txt"
    echo 3. 在 "规范管理" 中上传品牌规范文档 >> "品牌合规审核平台\使用说明.txt"
    echo 4. 在 "设计审核" 中上传设计稿进行审核 >> "品牌合规审核平台\使用说明.txt"
    echo. >> "品牌合规审核平台\使用说明.txt"
    echo 数据存储位置: data/ 目录下 >> "品牌合规审核平台\使用说明.txt"
    echo - data/rules/: 品牌规范文件 >> "品牌合规审核平台\使用说明.txt"
    echo - data/audit_history/: 审核历史记录 >> "品牌合规审核平台\使用说明.txt"
    echo - data/exports/: 导出的报告文件 >> "品牌合规审核平台\使用说明.txt"
)

cd ..

echo.
echo ========================================
echo   打包完成！
echo ========================================
echo.
echo 发布包位置: dist\品牌合规审核平台\
echo.
echo 使用方法:
echo   1. 将 "品牌合规审核平台" 文件夹复制给用户
echo   2. 双击 "启动程序.bat" 运行程序
echo.
pause