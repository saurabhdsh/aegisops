#!/usr/bin/env bash
# Start the API and the worker. Ctrl-C stops both.
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -d .venv || ! -f .env ]]; then
  echo "Run scripts/bootstrap.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
set -a
# shellcheck disable=SC1091
source .env
set +a

pids=()
cleanup() {
  local pid
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait || true
}
trap cleanup EXIT INT TERM

echo "API http://127.0.0.1:8000"
echo "OpenAPI http://127.0.0.1:8000/docs"
uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --reload &
pids+=("$!")
python -m workers.main &
pids+=("$!")
wait
