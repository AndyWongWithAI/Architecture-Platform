#!/bin/bash
# install-cron.sh — 在 #1 上注册架构平台备份 cron
# 用法:sudo bash /opt/services/arch-platform/deploy/install-cron.sh
#
# 注册两条 cron(避开业务高峰):
#   03:00 本地 SQLite 备份
#   04:00 异地 rsync 到 #2(单独 flag 触发)
#   每月 1 日 04:30 月度归档

set -e

APP_DIR="${APP_DIR:-/opt/services/arch-platform}"
BACKUP_SCRIPT="$APP_DIR/deploy/backup.sh"

if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo "ERROR: $BACKUP_SCRIPT 不存在" >&2
    exit 1
fi

chmod +x "$BACKUP_SCRIPT"

CRON_LINE_LOCAL="0 3 * * * $BACKUP_SCRIPT"
CRON_LINE_REMOTE="0 4 * * * REMOTE_BACKUP=1 $BACKUP_SCRIPT"
CRON_LINE_MONTHLY="30 4 1 * * MONTHLY_ARCHIVE=1 $BACKUP_SCRIPT"

# 读取现有 cron(若有)
EXISTING=$(crontab -l 2>/dev/null || echo "")

# 检查是否已注册(避免重复)
if echo "$EXISTING" | grep -qF "$BACKUP_SCRIPT"; then
    echo "[install-cron] 备份 cron 已存在,跳过"
    crontab -l | grep -F "$BACKUP_SCRIPT"
    exit 0
fi

# 注册新 cron(保留其他 cron,追加备份相关)
echo "$EXISTING" > /tmp/cron-backup
{
    echo "$CRON_LINE_LOCAL"
    echo "$CRON_LINE_REMOTE"
    echo "$CRON_LINE_MONTHLY"
} >> /tmp/cron-backup

crontab /tmp/cron-backup
rm -f /tmp/cron-backup

echo "[install-cron] 已注册:"
crontab -l | grep -F "$BACKUP_SCRIPT"

echo "[install-cron] ✅ 完成"