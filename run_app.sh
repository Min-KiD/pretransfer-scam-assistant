#!/usr/bin/env bash
# Start the app on this machine: http://localhost:${PORT:-8000}/  (needs GEMINI_API_KEY in .env)
set -euo pipefail
cd "$(dirname "$0")"
PORT=${PORT:-8000}
PY=.venv/bin/python
[[ -x $PY ]] || { python3 -m venv .venv && $PY -m pip install -q -r requirements.txt; }
echo "Mở http://localhost:$PORT/  (trang nhân viên: http://localhost:$PORT/web/staff.html)"
exec $PY -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
