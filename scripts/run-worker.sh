#!/usr/bin/env bash
# Run the scoring worker on the host against LocalStack.
# Prereqs: LocalStack up, .venv created, .env has GROQ_API_KEY set.
#   bash scripts/run-worker.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
  echo "No .venv — run: python3 -m venv .venv && . .venv/bin/activate && pip install -e shared -r services/worker/requirements.txt" >&2
  exit 1
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# pydantic-settings auto-loads ./.env; PYTHONPATH makes `app` resolve to the worker.
key=$(grep -E '^GROQ_API_KEY=' .env | cut -d= -f2-)
if [ -z "${key:-}" ]; then
  echo "WARNING: GROQ_API_KEY is empty in .env — resumes will fail scoring." >&2
fi

exec env PYTHONPATH=services/worker python -m app.main
