#!/bin/bash
# design-center-web 服务器部署（在服务器上执行）
set -e

NGINX_DIST="/usr/local/nginx/html/dist"
PACK_FILE="$NGINX_DIST/design-center-web/design-center-web-dist.tar.gz"
DEPLOY_DIR="$NGINX_DIST/design-center-web"
BACKUP_DIR="$NGINX_DIST/backup"
UNPACK_TMP="/tmp/design-center-web-unpack"

echo "=== [1/3] 备份旧版本 ==="
mkdir -p "$BACKUP_DIR"
if [ -d "$DEPLOY_DIR" ]; then
  mv "$DEPLOY_DIR" "$BACKUP_DIR/design-center-web_$(date +%Y%m%d_%H%M%S)"
fi
mkdir -p "$DEPLOY_DIR"

echo "=== [2/3] 解压新包 ==="
mkdir -p "$UNPACK_TMP"
rm -rf "${UNPACK_TMP:?}"/*
tar -xzf "$PACK_FILE" -C "$UNPACK_TMP"
if [ -d "$UNPACK_TMP/dist" ]; then
  cp -a "$UNPACK_TMP/dist/." "$DEPLOY_DIR/"
else
  cp -a "$UNPACK_TMP/." "$DEPLOY_DIR/"
fi
rm -f "$PACK_FILE"

echo "=== [3/3] 重载 Nginx ==="
/usr/local/nginx/sbin/nginx -t
/usr/local/nginx/sbin/nginx -s reload
echo "部署完成：https://172.30.95.244/"
