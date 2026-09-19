#!/usr/bin/env bash
# Start the CareerHelper FastAPI backend and Next.js frontend for local development.
#
# Usage: scripts/dev.sh
#   FastAPI: http://127.0.0.1:8000  (docs at /docs)
#   Next.js: http://localhost:3000
#
# The backend base URL and API key stay server-side; the browser only talks to
# Next.js. Override the venv with VENV=/path/to/venv if needed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${VENV:-$ROOT/.venv}"

if [ ! -x "$VENV/bin/uvicorn" ]; then
  echo "Creating Python venv at $VENV and installing backend deps..."
  python3 -m venv "$VENV"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip
  "$VENV/bin/python" -m pip install --quiet -e "$ROOT/backend[dev]"
fi

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  ( cd "$ROOT/frontend" && npm install )
fi

echo "Starting FastAPI on http://127.0.0.1:8000 ..."
( cd "$ROOT/backend" && "$VENV/bin/uvicorn" app.main:app --reload --port 8000 ) &
BACKEND_PID=$!

echo "Starting Next.js on http://localhost:3000 ..."
( cd "$ROOT/frontend" && FASTAPI_BASE_URL=http://127.0.0.1:8000 npm run dev ) &
FRONTEND_PID=$!

cleanup() {
  trap - INT TERM
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM

echo "CareerHelper is starting. Open http://localhost:3000 (Ctrl+C to stop)."
wait
