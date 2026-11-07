#!/usr/bin/env bash
# Migrate a temporary database, start the API and worker, and hit the health routes.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d .venv ]]; then
  echo "Run scripts/bootstrap.sh first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

tmp="$(mktemp -d)"
cleanup() {
  if [[ -n "${api_pid:-}" ]]; then kill "$api_pid" 2>/dev/null || true; fi
  if [[ -n "${worker_pid:-}" ]]; then kill "$worker_pid" 2>/dev/null || true; fi
  wait || true
  rm -rf "$tmp"
}
trap cleanup EXIT

export APP_SECRET="${APP_SECRET:-test-secret-key-must-be-at-least-32-characters}"
export APP_ENV=test
export EXECUTION_MODE=SIMULATOR
export DATABASE_URL="sqlite:///${tmp}/smoke.db"
export AUTONOMY_L4_ENABLED=false
export BOOTSTRAP_ADMIN_EMAIL=""
export BOOTSTRAP_ADMIN_PASSWORD=""

alembic upgrade head
uvicorn apps.api.main:app --host 127.0.0.1 --port 8765 &
api_pid=$!
python -m workers.main >"${tmp}/worker.log" 2>&1 &
worker_pid=$!

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://127.0.0.1:8765/health" >/dev/null; then
    break
  fi
  sleep 0.3
done

curl -sf "http://127.0.0.1:8765/health" | grep -q '"status":"ok"'
curl -sf "http://127.0.0.1:8765/ready" | grep -q '"status":"ready"'
curl -sf "http://127.0.0.1:8765/openapi.json" | grep -q '/api/v1/incidents'
code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8765/api/v1/incidents")"
test "$code" = "401"
sleep 1
grep -q "worker starting" "${tmp}/worker.log"
echo "smoke test passed"
