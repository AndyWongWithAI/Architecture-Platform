#!/bin/bash
# run.sh — 启动架构平台后端
#
# 用法:
#   ./run.sh dev        # 开发模式(auto-reload)
#   ./run.sh prod       # 生产模式(多 worker)
#   ./run.sh import     # 只导入 docs/components/*.md,不启动 server
#   ./run.sh test       # 跑测试

set -e
cd "$(dirname "$0")"

MODE="${1:-dev}"

case $MODE in
  dev)
    echo "[run] Starting dev server on http://127.0.0.1:8088"
    python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8088 --reload
    ;;
  prod)
    echo "[run] Starting prod server (4 workers) on http://127.0.0.1:8088"
    python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8088 --workers 4
    ;;
  import)
    echo "[run] Importing components from docs/components/*.md..."
    python3 scripts/import_components.py
    ;;
  test)
    echo "[run] Running tests..."
    python3 -m pytest tests/ -v
    ;;
  *)
    echo "Unknown mode: $MODE" >&2
    echo "Usage: $0 {dev|prod|import|test}" >&2
    exit 1
    ;;
esac