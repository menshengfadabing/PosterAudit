#!/bin/bash
# 后端重置（删除旧镜像和代码目录，在服务器上执行）
# 交互式询问是否同时清空数据卷（数据库数据）
set -e

DEPLOY_DIR="/opt/project/python_project/check_2"

echo "警告：将删除旧镜像和代码目录。设计到数据库字段变动时建议清空数据卷。"
read -r -p "确认继续？输入 yes 继续，其他任意键退出：" CONFIRM
if [ "$CONFIRM" != "yes" ]; then
  echo "已取消"
  exit 0
fi

read -r -p "是否同时删除数据卷并清空数据库？输入 yes 删除，其他任意键保留：" DROP_VOLUMES

if [ -d "$DEPLOY_DIR" ]; then
  cd "$DEPLOY_DIR"
  if [ "$DROP_VOLUMES" = "yes" ]; then
    echo "=== [1/3] 停止服务并删除数据卷 ==="
    docker compose --env-file .env.docker --profile infra --profile scale down -v --remove-orphans || true
  else
    echo "=== [1/3] 停止服务（保留数据卷） ==="
    docker compose --env-file .env.docker --profile infra --profile scale down --remove-orphans || true
  fi
fi

echo "=== [2/3] 删除旧镜像 ==="
docker rmi -f check_2-app:latest || true

echo "=== [3/3] 删除旧代码目录 ==="
rm -rf "$DEPLOY_DIR"

echo ""
echo "重置完成，请重新执行 02_backend_deploy.sh 部署"
