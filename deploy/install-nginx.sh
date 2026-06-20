#!/bin/bash
# install-nginx.sh — 在 #1 上配置架构平台 nginx 反代
# 前提:已部署 nginx,监听 8088 端口空闲

set -e

CONF_SRC="$(dirname "$0")/nginx-arch-platform.conf"
CONF_DST="/etc/nginx/sites-available/arch-platform"
LINK_DST="/etc/nginx/sites-enabled/arch-platform"

echo "[install-nginx] 检查 nginx..."
if ! command -v nginx >/dev/null 2>&1; then
    echo "ERROR: nginx 未安装" >&2
    exit 1
fi

if [ -f "$LINK_DST" ]; then
    echo "[install-nginx] WARN: $LINK_DST 已存在,先删除"
    rm -f "$LINK_DST"
fi

echo "[install-nginx] 复制配置 + 软链..."
cp "$CONF_SRC" "$CONF_DST"
chmod 644 "$CONF_DST"
ln -sf "$CONF_DST" "$LINK_DST"

echo "[install-nginx] 检查语法..."
nginx -t

echo "[install-nginx] 重载 nginx..."
systemctl reload nginx

echo "[install-nginx] 检查监听:"
ss -tlnp | grep :8088 || echo "WARN: 8088 未监听"

echo "[install-nginx] ✅ 完成"