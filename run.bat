@echo off
REM ShelfLoop one-command launcher (Windows).
REM Installs a local venv on first run, seeds the demo database, and serves the app.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.10+ is required. Install from https://python.org and retry.
  exit /b 1
)

if not exist "backend\.venv\Scripts\python.exe" (
  echo [shelfloop] creating virtual environment...
  python -m venv backend\.venv || exit /b 1
)

backend\.venv\Scripts\python -m pip install --quiet --disable-pip-version-check -r backend\requirements.txt || exit /b 1

echo [shelfloop] starting server on http://127.0.0.1:8000
echo   operator PIN 0000 - shop owner PIN 1234
start "" http://127.0.0.1:8000
backend\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --app-dir backend
