#!/bin/bash
# install-cron.sh — 在 #1 上注册架构平台备份 cron
# 用法:sudo bash /opt/services/arch-platform/deploy/install-cron.sh
#
# 注册 cron:
#   每 4 小时(00/04/08/12/16/20):本地 + 异地合并备份
#                                  本地 SQLite 备份 + rsync → #2 81.71.132.24
#   每月 1 日 04:30:月度归档
#
# 2026-06-21 修订:从原本地每日 03:00 + 异地每日 04:00 双 cron,
#                  合并为每 4 小时一次本地+异地(数据更安全,频率更高)。

set -e

APP_DIR="${APP_DIR:-/opt/services/arch-platform}"
BACKUP_SCRIPT="$APP_DIR/deploy/backup.sh"

if [ ! -f "$BACKUP_SCRIPT" ]; then
    echo "ERROR: $BACKUP_SCRIPT 不存在" >&2
    exit 1
fi

chmod +x "$BACKUP_SCRIPT"

# 每 4 小时:本地 + 异地(REMOTE_BACKUP=1 同时触发)
CRON_LINE_REMOTE="0 */4 * * * REMOTE_BACKUP=1 $BACKUP_SCRIPT"
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
    echo "$CRON_LINE_REMOTE"
    echo "$CRON_LINE_MONTHLY"
} >> /tmp/cron-backup

crontab /tmp/cron-backup
rm -f /tmp/cron-backup

echo "[install-cron] 已注册:"
crontab -l | grep -F "$BACKUP_SCRIPT"

echo "[install-cron] ✅ 完成"
