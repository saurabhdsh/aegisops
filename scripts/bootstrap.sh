#!/usr/bin/env bash
# Create the virtualenv, install the package, and migrate the local database.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v python3.12 >/dev/null 2>&1; then
  echo "python3.12 is required" >&2
  exit 1
fi

python3.12 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

python - <<'PY'
import secrets
from pathlib import Path

path = Path(".env")
lines = []
for line in path.read_text().splitlines():
    key, _, value = line.partition("=")
    if key == "APP_SECRET" and len(value) < 32:
        lines.append("APP_SECRET=" + secrets.token_urlsafe(48))
    else:
        lines.append(line)
path.write_text("\n".join(lines) + "\n")
print("APP_SECRET is present in .env. The value was not printed.")
PY

set -a
# shellcheck disable=SC1091
source .env
set +a
alembic upgrade head
echo "Database migrated. Start the processes with ./dev.sh"
