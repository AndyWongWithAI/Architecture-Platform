#!/bin/bash
# install-systemd.sh — 在 #1 上注册 arch-platform systemd 服务
# 用法:ssh root@124.71.219.208 'bash -s' < install-systemd.sh
# 前提:已部署 docker-compose.yml 到 /opt/services/arch-platform/

set -e

SERVICE_FILE="/etc/systemd/system/arch-platform.service"
APP_DIR="/opt/services/arch-platform"

echo "[install-systemd] 检查应用目录..."
if [ ! -f "$APP_DIR/docker-compose.yml" ]; then
    echo "ERROR: $APP_DIR/docker-compose.yml 不存在,先部署应用" >&2
    exit 1
fi

if [ ! -f "$APP_DIR/.env" ]; then
    echo "WARN: $APP_DIR/.env 不存在,从 .env.example 复制(API Key 留空=开放模式)"
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

echo "[install-systemd] 复制 service 文件..."
cp "$(dirname "$0")/arch-platform.service" "$SERVICE_FILE"
chmod 644 "$SERVICE_FILE"

echo "[install-systemd] 重载 systemd daemon..."
systemctl daemon-reload

echo "[install-systemd] 启用并启动服务..."
systemctl enable --now arch-platform.service

echo "[install-systemd] 等待 10s 让容器启动..."
sleep 10

echo "[install-systemd] 检查状态:"
systemctl status arch-platform.service --no-pager --lines=10 || true

echo "[install-systemd] 健康检查:"
curl -s http://127.0.0.1:8088/healthz && echo "" || echo "HEALTHZ FAILED"

echo "[install-systemd] ✅ 完成"