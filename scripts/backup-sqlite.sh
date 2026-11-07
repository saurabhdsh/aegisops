#!/usr/bin/env bash
# Copy the configured SQLite database. PostgreSQL backups are not performed by this script.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
url="${DATABASE_URL:-sqlite:///./aegisops.db}"
case "$url" in
  sqlite:///*) source="${url#sqlite:///}" ;;
  sqlite:*) source="${url#sqlite:}" ;;
  *)
    echo "DATABASE_URL is not SQLite. This script only copies a local SQLite file." >&2
    exit 1
    ;;
esac
if [[ ! -f "$source" ]]; then
  echo "Database file not found: $source" >&2
  exit 1
fi
destination="${1:-backups/aegisops-$(date -u +%Y%m%dT%H%M%SZ).db}"
mkdir -p "$(dirname "$destination")"
cp "$source" "$destination"
echo "copied $source to $destination"
