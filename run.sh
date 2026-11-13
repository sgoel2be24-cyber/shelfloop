#!/usr/bin/env bash
# ShelfLoop one-command launcher (macOS/Linux/Git Bash).
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10+ is required." && exit 1
fi

if [ ! -x "backend/.venv/bin/python" ] && [ ! -x "backend/.venv/Scripts/python.exe" ]; then
  echo "[shelfloop] creating virtual environment..."
  python3 -m venv backend/.venv
fi

PY="backend/.venv/bin/python"
[ -x "$PY" ] || PY="backend/.venv/Scripts/python.exe"

"$PY" -m pip install --quiet -r backend/requirements.txt

echo "[shelfloop] starting server on http://127.0.0.1:8000"
echo "  operator PIN 0000 - shop owner PIN 1234"
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
