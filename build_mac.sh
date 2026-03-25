#!/bin/bash
# ========================================
# 品牌合规审核平台 - macOS 打包脚本
# ========================================

set -e

echo ""
echo "========================================"
echo "  品牌合规审核平台 - macOS 打包工具"
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
    echo "建议使用 Homebrew 安装: brew install python3"
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

if [ ! -f "dist/品牌合规审核平台.app/Contents/MacOS/品牌合规审核平台" ]; then
    echo -e "${RED}[错误] 打包失败，请检查错误信息${NC}"
    exit 1
fi

echo -e "${GREEN}[5/5] 创建发布包...${NC}"
cd dist

# 创建发布目录
PACKAGE_NAME="品牌合规审核平台-macOS"
rm -rf "$PACKAGE_NAME"
mkdir -p "$PACKAGE_NAME"

# 移动 .app 文件
cp -r "品牌合规审核平台.app" "$PACKAGE_NAME/"

# 复制数据目录
cp -r ../data "$PACKAGE_NAME/"
cp -r ../config "$PACKAGE_NAME/"

# 创建启动脚本
cat > "$PACKAGE_NAME/启动程序.command" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
open "品牌合规审核平台.app"
EOF
chmod +x "$PACKAGE_NAME/启动程序.command"

# 创建使用说明
cat > "$PACKAGE_NAME/使用说明.txt" << 'EOF'
品牌合规审核平台
================================

使用方法:
1. 双击 "品牌合规审核平台.app" 或 "启动程序.command"
2. 首次使用请先在 "API设置" 中配置 API Key
3. 在 "规范管理" 中上传品牌规范文档
4. 在 "设计审核" 中上传设计稿进行审核

数据存储位置: data/ 目录下
- data/rules/: 品牌规范文件
- data/audit_history/: 审核历史记录
- data/exports/: 导出的报告文件

注意事项:
1. 首次打开可能提示"无法验证开发者"，请按以下步骤操作:
   - 系统偏好设置 -> 安全性与隐私 -> 通用
   - 点击"仍要打开"或"打开 anyway"

2. 或者在终端运行:
   xattr -cr "品牌合规审核平台.app"

3. 如需创建应用程序别名到 /Applications:
   cp -r "品牌合规审核平台.app" /Applications/
EOF

# 创建安装脚本
cat > "$PACKAGE_NAME/安装到应用程序文件夹.sh" << 'EOF'
#!/bin/bash
echo "正在安装到 /Applications/ ..."
cp -r "品牌合规审核平台.app" /Applications/
echo "安装完成！"
echo "您可以从 Launchpad 或 /Applications/ 启动程序"
EOF
chmod +x "$PACKAGE_NAME/安装到应用程序文件夹.sh"

# 创建 DMG 镜像（如果 hdiutil 可用）
if command -v hdiutil &> /dev/null; then
    echo "正在创建 DMG 镜像..."
    hdiutil create -volname "品牌合规审核平台" \
        -srcfolder "$PACKAGE_NAME" \
        -ov -format UDZO \
        "$PACKAGE_NAME.dmg"
fi

cd ..

echo ""
echo -e "${GREEN}========================================"
echo "  打包完成！"
echo "========================================${NC}"
echo ""
echo "发布包位置: dist/$PACKAGE_NAME/"
if [ -f "dist/$PACKAGE_NAME.dmg" ]; then
    echo "DMG 镜像: dist/$PACKAGE_NAME.dmg"
fi
echo ""
echo "使用方法:"
echo "  1. 将 .app 文件拖入 /Applications/ 或双击运行"
echo "  2. 首次运行可能需要在终端执行: xattr -cr 品牌合规审核平台.app"
echo ""