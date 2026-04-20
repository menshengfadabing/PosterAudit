#!/usr/bin/env bash
set -euo pipefail

# 必填：数据库连接串 + 初始管理员账号
: "${DATABASE_URL:?need DATABASE_URL, e.g. postgresql://postgres:xxx@127.0.0.1:5432/app}"
: "${INIT_ADMIN_USER:?need INIT_ADMIN_USER, e.g. yzhuo}"

# 可选：管理员显示名
INIT_ADMIN_NAME="${INIT_ADMIN_NAME:-$INIT_ADMIN_USER}"

psql "$DATABASE_URL" <<SQL
INSERT INTO users (id, name, role, status, created_at, updated_at)
VALUES ('${INIT_ADMIN_USER}', '${INIT_ADMIN_NAME}', 'admin', 'active', NOW(), NOW())
ON CONFLICT (id) DO UPDATE
SET role = 'admin',
    status = 'active',
    name = EXCLUDED.name,
    updated_at = NOW();
SQL

echo "Init admin done: user=${INIT_ADMIN_USER}"