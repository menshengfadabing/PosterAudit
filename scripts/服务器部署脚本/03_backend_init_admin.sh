#!/bin/bash
# 初始化/修复管理员账号（在服务器上执行）
set -e

DEPLOY_DIR="/opt/project/python_project/check_2"
cd "$DEPLOY_DIR"

echo "=== 插入或更新管理员账号 yzhuo ==="
docker compose exec -T postgres psql -U audit_user -d audit_platform -c \
  "INSERT INTO users (id, name, role, status, created_at, updated_at)
   VALUES ('yzhuo', '霍源治', 'admin', 'active', NOW(), NOW())
   ON CONFLICT (id) DO UPDATE
   SET role='admin', status='active', name=EXCLUDED.name, updated_at=NOW();"

echo ""
echo "=== 当前管理员列表 ==="
docker compose exec -T postgres psql -U audit_user -d audit_platform -c \
  "SELECT id, name, role FROM users WHERE role='admin';"
