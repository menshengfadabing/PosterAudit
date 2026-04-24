#!/bin/bash
# 后端本地打包 + 上传服务器
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="/home/admin123/project/AI_project/check_2"
PACK_FILE="/home/admin123/project/AI_project/check_2_release.tar.gz"
SERVER="root@172.30.95.244"
SERVER_PASS="2026@DMS_new"
SERVER_PATH="/opt/project/python_project/"

echo "=== [1/2] 打包后端 ==="
cd "$BACKEND_DIR"
tar -czf "$PACK_FILE" \
  --exclude=.git \
  --exclude=.venv \
  --exclude=__pycache__ \
  --exclude='*.pyc' \
  --exclude=.pytest_cache \
  --exclude=logs \
  --exclude=data/uploads \
  --exclude=data/audit_history \
  .
echo "打包完成：$PACK_FILE"

echo "=== [2/2] 上传到服务器 ==="
sshpass -p "$SERVER_PASS" scp "$PACK_FILE" "$SERVER:$SERVER_PATH"
echo "上传完成"
echo ""
echo "下一步：在服务器上执行 02_backend_deploy.sh"
