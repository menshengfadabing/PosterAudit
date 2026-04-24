#!/bin/bash
# 后端服务器部署（在服务器上执行）
# 首次部署 or 仅重建镜像（不清数据）
set -e

DEPLOY_DIR="/opt/project/python_project/check_2"
PACK_FILE="/opt/project/python_project/check_2_release.tar.gz"

echo "=== [1/4] 解压后端发布包 ==="
mkdir -p "$DEPLOY_DIR"
tar -xzf "$PACK_FILE" -C "$DEPLOY_DIR"
cd "$DEPLOY_DIR"

echo "=== [2/4] 停止旧容器并删除旧镜像 ==="
docker compose --env-file .env.docker down --remove-orphans || true
docker rmi -f check_2-app:latest || true

echo "=== [3/4] 构建新镜像 ==="
docker compose --env-file .env.docker build api celery1

echo "=== [4/4] 启动服务 ==="
docker compose --env-file .env.docker --profile infra up -d api celery1 postgres redis --remove-orphans

echo ""
echo "=== 健康检查 ==="
sleep 5
curl -si http://127.0.0.1:18080/health | head -5
echo ""
echo "=== 验证 Celery 并发配置 ==="
docker exec check2-celery1 cat /proc/1/cmdline | tr '\0' ' '
echo ""
echo "部署完成"
echo "如需插入管理员账号，执行 03_backend_init_admin.sh"
