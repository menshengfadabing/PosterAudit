#!/bin/bash
# design-center-web 本地构建 + 上传服务器
set -e

FRONT_DIR="/home/admin123/project/AI_project/sourcecode/design-center-web"
PACK_FILE="$FRONT_DIR/design-center-web-dist.tar.gz"
SERVER="root@172.30.95.244"
SERVER_PASS="2026@DMS_new"
SERVER_PATH="/usr/local/nginx/html/dist/design-center-web/"

echo "=== [1/3] 安装依赖 ==="
cd "$FRONT_DIR"
pnpm install

echo "=== [2/3] 构建（test 环境） ==="
pnpm build:test

echo "=== [3/3] 打包并上传 ==="
tar -czf "$PACK_FILE" -C dist .
sshpass -p "$SERVER_PASS" scp "$PACK_FILE" "$SERVER:$SERVER_PATH"
rm -f "$PACK_FILE"
echo "上传完成"
echo ""
echo "下一步：在服务器上执行 08_frontend_center_deploy.sh"
