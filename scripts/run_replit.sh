#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -x "$ROOT/.venv/bin/python" ] || { echo '[ERROR] .venv missing. Run bash scripts/setup_replit.sh first.'; exit 1; }
[ -f "$ROOT/frontend/dist/index.html" ] || { echo '[ERROR] Frontend build missing. Run bash scripts/setup_replit.sh first.'; exit 1; }
cd "$ROOT/backend"
exec "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-5000}" --proxy-headers
