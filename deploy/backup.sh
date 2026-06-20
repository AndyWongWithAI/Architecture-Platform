#!/bin/bash
# backup.sh — 架构平台数据备份脚本
# 用法:sudo bash /opt/services/arch-platform/deploy/backup.sh
# 部署后注册 cron:
#   03:00 本地备份(.backup 命令 → /opt/services/arch-platform/backups/)
#   04:00 异地备份(rsync → #2 81.71.132.24)
#
# 备份策略:
#   - 全量备份保留 30 天(每日一个文件,命名:arch-YYYYMMDD.db)
#   - 异地备份永久保留(命名:arch-YYYYMMDD.db,跟本地同)
#   - 用 SQLite 原生 .backup 命令,避免 cp 在事务中损坏 DB
#   - 备份后 SHA256 校验,记录日志
#   - 每月归档一份 tar.gz 到 /opt/services/arch-platform/backups/monthly/
#
# 备份脚本单独配置项(可覆盖):
#   APP_DIR    默认 /opt/services/arch-platform
#   BACKUP_DIR 默认 $APP_DIR/backups
#   REMOTE_HOST 默认 81.71.132.24(同 ssh-config alias: server-2)
#   REMOTE_DIR 默认 /opt/services/arch-platform-backups

set -euo pipefail

# ——— 配置 ———
APP_DIR="${APP_DIR:-/opt/services/arch-platform}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
DB_PATH="${ARCH_DB_PATH:-$APP_DIR/data/arch.db}"
REMOTE_HOST="${REMOTE_HOST:-81.71.132.24}"
REMOTE_DIR="${REMOTE_DIR:-/opt/services/arch-platform-backups}"
REMOTE_USER="${REMOTE_USER:-root}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

# ——— 准备 ———
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DATE="$(date +%Y%m%d)"
BACKUP_FILE="$BACKUP_DIR/arch-$DATE.db"
LOG_FILE="$BACKUP_DIR/backup.log"
MONTHLY_DIR="$BACKUP_DIR/monthly"

mkdir -p "$BACKUP_DIR" "$MONTHLY_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# ——— 前置检查 ———
if [ ! -f "$DB_PATH" ]; then
    log "ERROR: 数据库文件不存在: $DB_PATH"
    exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    log "ERROR: sqlite3 命令未安装"
    exit 1
fi

# ——— 1. 全量备份(本地) ———
log "开始本地备份: $DB_PATH → $BACKUP_FILE"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"
BACKUP_SIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || stat -f%z "$BACKUP_FILE")
log "本地备份完成: $BACKUP_FILE ($((BACKUP_SIZE / 1024)) KB)"

# ——— 2. SHA256 校验(写日志,便于定期核查) ———
SHA256=$(sha256sum "$BACKUP_FILE" | awk '{print $1}')
log "SHA256: $SHA256"

# ——— 3. 清理 30 天前的旧备份 ———
DELETED=$(find "$BACKUP_DIR" -maxdepth 1 -name "arch-*.db" -mtime +$RETENTION_DAYS -print -delete | wc -l)
if [ "$DELETED" -gt 0 ]; then
    log "清理 $RETENTION_DAYS 天前的备份: $DELETED 个文件"
fi

# ——— 4. 异地备份(每日 04:00 cron) ———
# 单独通过 flag 控制,避免同一次 cron 同时跑两个动作造成 SSH 连接堆积
if [ "${REMOTE_BACKUP:-0}" = "1" ]; then
    log "开始异地备份: $REMOTE_HOST:$REMOTE_DIR"
    if ! command -v rsync >/dev/null 2>&1; then
        log "ERROR: rsync 未安装"
        exit 1
    fi
    # 用 ssh 指定私钥,避免密码交互
    RSYNC_SSH="${RSYNC_SSH:-ssh -i /root/.ssh/arch-platform-backup -o StrictHostKeyChecking=accept-new}"
    # --mkpath 自动创建远程目录(rsync >= 3.2.3);Ubuntu 24.04 自带 3.2.7+
    rsync -avz --mkpath -e "$RSYNC_SSH" "$BACKUP_FILE" "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/" \
        >> "$LOG_FILE" 2>&1
    log "异地备份完成"
fi

# ——— 5. 月度归档(每月 1 日执行) ———
if [ "${MONTHLY_ARCHIVE:-0}" = "1" ]; then
    MONTH=$(date +%Y%m)
    ARCHIVE="$MONTHLY_DIR/arch-$MONTH.tar.gz"
    log "生成月度归档: $ARCHIVE"
    tar -czf "$ARCHIVE" -C "$BACKUP_DIR" "arch-$DATE.db" 2>> "$LOG_FILE"
    log "月度归档完成: $ARCHIVE"
fi

log "✅ 备份完成"