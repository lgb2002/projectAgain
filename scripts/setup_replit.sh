#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v python3 >/dev/null || { echo '[ERROR] python3 not installed. Add Python runtime manually, not via Agent.'; exit 1; }
command -v npm >/dev/null || { echo '[ERROR] npm not installed. Add Node.js runtime manually, not via Agent.'; exit 1; }
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3 -m venv "$ROOT/.venv"
fi
export PIP_CONFIG_FILE=/dev/null
export PIP_USER=0
"$ROOT/.venv/bin/python" -m pip install --no-user -r "$ROOT/backend/requirements-dev.txt"
if [ "${PRIVATE_STORAGE_BACKEND:-}" = 'replit' ] || [ "${APP_ENV:-}" = 'production' ]; then
  "$ROOT/.venv/bin/python" -m pip install --no-user -r "$ROOT/backend/requirements-storage.txt"
fi
echo '[SETUP] Build frontend ...'
(cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
echo '[SETUP] Apply migrations ...'
(cd "$ROOT/backend" && "$ROOT/.venv/bin/python" -m alembic upgrade head)
echo '[SETUP] Success. Run: bash scripts/run_replit.sh'
