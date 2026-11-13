#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
CHECK_FRONTEND=0 bash scripts/check_project_v012.sh
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
(cd "$ROOT/backend" && "$PY" -m pytest -q tests/test_privacy_readiness_v013.py)
(cd "$ROOT/backend" && "$PY" -m compileall -q app alembic/versions)
if [ "${CHECK_FRONTEND:-0}" = "1" ]; then
  (cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
fi
echo '[PASS] v0.13 backend test groups, privacy/report tests and Python compile. Frontend only if CHECK_FRONTEND=1.'
