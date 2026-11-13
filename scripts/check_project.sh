#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
python -m pytest -q
python -m compileall -q app
cd "$ROOT"
echo '[OK] Backend tests and Python compile completed.'
if [ "${CHECK_FRONTEND:-0}" = '1' ];then
  cd "$ROOT/frontend"
  npm run build
  echo '[OK] Frontend compiled'
else
  echo '[NOTE] Set CHECK_FRONTEND=1 to run npm build after npm install.'
fi
