#!/bin/bash
# ========================================
# 品牌合规审核平台 - 自动打包脚本
# 自动检测当前平台并执行对应的打包流程
# ========================================

set -e

echo ""
echo "========================================"
echo "  品牌合规审核平台 - 自动打包工具"
echo "========================================"
echo ""

# 检测操作系统
OS="$(uname -s)"
case "$OS" in
    Linux*)     MACHINE=Linux;;
    Darwin*)    MACHINE=Mac;;
    CYGWIN*)    MACHINE=Cygwin;;
    MINGW*)     MACHINE=MinGw;;
    *)          MACHINE="UNKNOWN:$OS"
esac

echo "检测到平台: $MACHINE"
echo ""

# 执行对应的打包脚本
case "$MACHINE" in
    Linux)
        echo "执行 Linux 打包..."
        chmod +x build_linux.sh
        ./build_linux.sh
        ;;
    Mac)
        echo "执行 macOS 打包..."
        chmod +x build_mac.sh
        ./build_mac.sh
        ;;
    Cygwin|MinGw)
        echo "检测到 Windows 环境，请使用 build_windows.bat"
        echo "或直接在 CMD/PowerShell 中运行 build_windows.bat"
        exit 1
        ;;
    *)
        echo "未知平台: $MACHINE"
        echo "请手动运行对应的打包脚本"
        exit 1
        ;;
esac