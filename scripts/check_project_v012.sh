#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY=python3
cd "$ROOT/backend"
"$PY" -m pytest -q tests/test_integrated_workspace_v012.py tests/test_deal_management_v08.py tests/test_development_roadmap_v09.py
"$PY" -m pytest -q tests/test_marketplace_v07.py tests/test_notification_unread_v11.py tests/test_phase2.py
"$PY" -m pytest -q tests/test_agent_listing_proposals.py tests/test_inspection_access.py tests/test_integration_v05.py tests/test_project_imports.py
"$PY" -m pytest -q tests/test_workflows.py
"$PY" -m compileall -q app
if [ "${CHECK_FRONTEND:-0}" = "1" ]; then
 (cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
fi
echo '[PASS] v0.12 separated backend suites. Frontend checked only with CHECK_FRONTEND=1.'
