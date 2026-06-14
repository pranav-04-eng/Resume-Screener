#!/usr/bin/env bash
# Stop everything started by run-local.sh and tear down LocalStack.
#   bash scripts/run-stop.sh
set -uo pipefail
cd "$(dirname "$0")/.."
LOG_DIR=".local-logs"

if [ -f "$LOG_DIR/pids" ]; then
  while read -r pid; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null && echo "killed pid $pid"
  done < "$LOG_DIR/pids"
  : > "$LOG_DIR/pids"
fi

# Belt-and-suspenders for any strays.
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "PYTHONPATH=services/worker" 2>/dev/null || true
pkill -f "app.main" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true

docker compose down >/dev/null 2>&1 || true
echo "==> Local stack stopped."
