#!/bin/bash
# ========================================
# 品牌合规审核平台 - Linux 打包脚本
# ========================================

set -e

echo ""
echo "========================================"
echo "  品牌合规审核平台 - Linux 打包工具"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[错误] 未检测到 Python3，请先安装 Python 3.10+${NC}"
    echo "Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "CentOS/RHEL: sudo yum install python3 python3-pip"
    exit 1
fi

echo -e "${GREEN}[1/5] 安装依赖包...${NC}"
pip3 install pyinstaller -q 2>/dev/null || pip install pyinstaller -q
pip3 install -r requirements.txt -q 2>/dev/null || pip3 install pyside6 pyside6-fluent-widgets langchain-openai pymupdf python-pptx python-docx openpyxl xlrd pillow pydantic pydantic-settings httpx -q

echo -e "${GREEN}[2/5] 创建必要目录...${NC}"
mkdir -p data/rules
mkdir -p data/audit_history
mkdir -p data/exports
mkdir -p data/uploads

echo -e "${GREEN}[3/5] 清理旧的打包文件...${NC}"
rm -rf dist build

echo -e "${GREEN}[4/5] 开始打包 (这可能需要几分钟)...${NC}"
pyinstaller build.spec --noconfirm --clean

if [ ! -f "dist/BrandAudit" ]; then
    echo -e "${RED}[错误] 打包失败，请检查错误信息${NC}"
    exit 1
fi

echo -e "${GREEN}[5/5] 创建发布包...${NC}"
cd dist

# 创建发布目录
PACKAGE_NAME="品牌合规审核平台-Linux"
rm -rf "$PACKAGE_NAME"
mkdir -p "$PACKAGE_NAME"

# 移动可执行文件
mv BrandAudit "$PACKAGE_NAME/"
chmod +x "$PACKAGE_NAME/BrandAudit"

# 复制数据目录
cp -r ../data "$PACKAGE_NAME/"
cp -r ../config "$PACKAGE_NAME/"

# 创建启动脚本
cat > "$PACKAGE_NAME/启动程序.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)
./BrandAudit "$@"
EOF
chmod +x "$PACKAGE_NAME/启动程序.sh"

# 创建桌面快捷方式模板
cat > "$PACKAGE_NAME/创建桌面快捷方式.sh" << 'EOF'
#!/bin/bash
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
DESKTOP_FILE="$HOME/Desktop/品牌合规审核平台.desktop"

cat > "$DESKTOP_FILE" << DESKTOP
[Desktop Entry]
Version=1.0
Type=Application
Name=品牌合规审核平台
Comment=品牌合规性智能审核平台
Exec="$APP_DIR/启动程序.sh"
Icon="$APP_DIR/config/icon.png"
Terminal=false
Categories=Utility;Graphics;
DESKTOP

chmod +x "$DESKTOP_FILE"
echo "桌面快捷方式已创建: $DESKTOP_FILE"
EOF
chmod +x "$PACKAGE_NAME/创建桌面快捷方式.sh"

# 创建使用说明
cat > "$PACKAGE_NAME/使用说明.txt" << 'EOF'
品牌合规审核平台
================================

使用方法:
1. 双击 "启动程序.sh" 或在终端运行 ./启动程序.sh
2. 首次使用请先在 "API设置" 中配置 API Key
3. 在 "规范管理" 中上传品牌规范文档
4. 在 "设计审核" 中上传设计稿进行审核

数据存储位置: data/ 目录下
- data/rules/: 品牌规范文件
- data/audit_history/: 审核历史记录
- data/exports/: 导出的报告文件

注意:
- 首次运行可能需要授予执行权限: chmod +x 启动程序.sh
- 如需创建桌面快捷方式，运行: ./创建桌面快捷方式.sh
EOF

# 创建 tar.gz 压缩包
tar -czf "$PACKAGE_NAME.tar.gz" "$PACKAGE_NAME"

cd ..

echo ""
echo -e "${GREEN}========================================"
echo "  打包完成！"
echo "========================================${NC}"
echo ""
echo "发布包位置: dist/$PACKAGE_NAME/"
echo "压缩包位置: dist/$PACKAGE_NAME.tar.gz"
echo ""
echo "使用方法:"
echo "  1. 解压后将文件夹复制给用户"
echo "  2. 运行 ./启动程序.sh"
echo ""