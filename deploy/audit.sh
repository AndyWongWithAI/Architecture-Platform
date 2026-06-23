#!/bin/bash
# arch-platform 定时自审包装器(每日 04:00 cron)
# 链路:
#   1. scan.py 跑全量 9 原则扫描 → JSON 文件
#   2. POST JSON 到后端 /api/v1/audit/runs → 落库 AuditRun + AuditFinding
#   3. 失败:文件移到 specs/audit-reports/failed/ + 通过 cron-with-feedback 通知
#
# 部署位置:#1 /opt/services/arch-platform/deploy/audit.sh
# 由 deploy/install-cron.sh 注册到主机 crontab。
# flock 防止与 audit-skill 周日 04:15 撞车(那个 cron 会写 .workflow-lock)。

set -euo pipefail

SCAN_BIN=/home/hq/.claude/skills/audit/scripts/scan.py
ARCH_URL=${ARCH_PLATFORM_URL:-http://127.0.0.1:8088}
TS=$(date +%Y%m%d-%H%M%S)
JSON=/tmp/arch-audit-${TS}.json
LOG=/var/log/arch-platform-audit.log
LOCK=/home/hq/.claude/specs/audit-reports/.arch-cron.lock
FEEDBACK_BIN=/home/hq/.claude/bin/cron-with-feedback.sh

# flock 防止与 audit-skill 周日 04:15 撞车
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[$(date '+%F %T')] audit 锁定中,跳过本次" >> "$LOG"
  exit 0
fi

echo "[$(date '+%F %T')] arch-platform 04:00 self-audit start" >> "$LOG"

# 1. scan.py 跑全量
if ! python3 "$SCAN_BIN" --scope=all --severity-min=info --gate=hard --json > "$JSON" 2>>"$LOG"; then
  echo "[$(date '+%F %T')] scan 失败,见 $LOG" >> "$LOG"
  [ -x "$FEEDBACK_BIN" ] && "$FEEDBACK_BIN" arch-audit-fail "scan.py exit=$?" || true
  exit 1
fi

# 2. POST 到后端
if ! curl -fsS -X POST "$ARCH_URL/api/v1/audit/runs" \
  -H "X-API-Key: ${ARCH_PLATFORM_API_KEY:-}" \
  -H "Content-Type: application/json" \
  -d @"$JSON" >> "$LOG" 2>&1; then
  echo "[$(date '+%F %T')] POST 失败,文件移到 failed/" >> "$LOG"
  mkdir -p /home/hq/.claude/specs/audit-reports/failed
  mv "$JSON" /home/hq/.claude/specs/audit-reports/failed/
  [ -x "$FEEDBACK_BIN" ] && "$FEEDBACK_BIN" arch-audit-fail "POST $ARCH_URL fail" || true
  exit 1
fi

rm -f "$JSON"
echo "[$(date '+%F %T')] arch-platform 04:00 self-audit done" >> "$LOG"