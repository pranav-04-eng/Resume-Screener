#!/usr/bin/env bash
# One-command local stack: LocalStack + intake + results + worker + frontend.
# Logs go to .local-logs/, PIDs to .local-logs/pids so run-stop.sh can clean up.
#   bash scripts/run-local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
LOG_DIR="$ROOT/.local-logs"
mkdir -p "$LOG_DIR"
: > "$LOG_DIR/pids"

note() { printf "\033[36m==> %s\033[0m\n" "$*"; }

# ── prereqs ──────────────────────────────────────────────────────────────
if [ ! -d .venv ]; then
  note "Creating .venv and installing backend deps (first run only)…"
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -q -e shared \
    -r services/intake/requirements.txt \
    -r services/results/requirements.txt \
    -r services/worker/requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

[ -f .env ] || { cp .env.example .env; note "Created .env from example — set GROQ_API_KEY for scoring."; }
set -a; . ./.env; set +a

# ── 1. LocalStack ────────────────────────────────────────────────────────
note "Starting LocalStack…"
docker compose up -d localstack >/dev/null
for _ in $(seq 1 30); do
  curl -sf http://localhost:4566/_localstack/health >/dev/null 2>&1 && break
  sleep 2
done
note "LocalStack ready (S3 / DynamoDB / SQS)."

start() {  # start <name> <port-or-->  <command...>
  local name="$1" port="$2"; shift 2
  note "Starting $name${port:+ (:$port)}…"
  ( "$@" >"$LOG_DIR/$name.log" 2>&1 & echo "$!" >>"$LOG_DIR/pids" )
}

# ── 2-4. backend services ──────────────────────────────────────────────────
start intake  8001 uvicorn app.main:app --app-dir services/intake  --host 0.0.0.0 --port 8001
start results 8002 uvicorn app.main:app --app-dir services/results --host 0.0.0.0 --port 8002
start worker  "" env PYTHONPATH=services/worker python -m app.main

# ── 5. frontend ────────────────────────────────────────────────────────────
if [ ! -d frontend/node_modules ]; then
  note "Installing frontend deps (first run only)…"
  ( cd frontend && npm install >/dev/null 2>&1 )
fi
[ -f frontend/.env ] || cp frontend/.env.example frontend/.env
start frontend 5173 bash -c "cd frontend && npm run dev"

sleep 4
echo
note "Local stack is up:"
echo "   Frontend : http://localhost:5173  (or 5174 if 5173 was taken — check .local-logs/frontend.log)"
echo "   Intake   : http://localhost:8001/healthz"
echo "   Results  : http://localhost:8002/healthz"
echo "   Logs     : $LOG_DIR/*.log     Stop: bash scripts/run-stop.sh"
if [ -z "${GROQ_API_KEY:-}" ]; then
  echo
  printf "\033[33m   ⚠ GROQ_API_KEY is empty — set it in .env and restart the worker to enable scoring.\033[0m\n"
fi
