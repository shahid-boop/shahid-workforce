@echo off
rem ============================================================================
rem  Shahid Workforce - one-click local dev starter (Windows)
rem
rem  Double-click to start everything:
rem    1. FastAPI API on http://127.0.0.1:8000
rem    2. Next.js dashboard on http://localhost:3000
rem    3. Opens the dashboard in your default browser
rem
rem  Uses the repo-local .venv and apps/dashboard\node_modules; no manual
rem  environment variables needed. Tasks auto-run inline in development
rem  (WORKFORCE_AUTO_RUN defaults to on when WORKFORCE_ENV is not
rem  "production"), so no Redis or worker process is required.
rem
rem  Close this window (or press Ctrl+C twice) to stop everything.
rem ============================================================================
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

rem --- required configuration ------------------------------------------------
set "WORKFORCE_API_KEY=local-dev-key"
set "WORKFORCE_DATABASE_URL=sqlite:///%ROOT%workforce.db"
set "WORKFORCE_CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000"
set "WORKFORCE_AUTO_RUN=1"
set "WORKFORCE_API_BASE_URL=http://127.0.0.1:8000"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment...
  py -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install -q -e ".[dev]" || goto :fail
)
if not exist "apps\dashboard\node_modules" (
  echo [setup] Installing dashboard dependencies...
  pushd apps\dashboard
  npm.cmd install || (popd & goto :fail)
  popd
)

rem --- run migrations so the schema is fresh ---------------------------------
".venv\Scripts\python.exe" -m alembic upgrade head || goto :fail

echo.
echo ============================================================
echo  Shahid Workforce starting
echo    API       http://127.0.0.1:8000/docs
echo    Dashboard http://localhost:3000
echo    Settings  http://localhost:3000/settings   (add provider keys)
echo  Close this window to stop both servers.
echo ============================================================
echo.

rem --- start dashboard (second window) ---------------------------------------
start "Shahid Dashboard" powershell -NoExit -Command ^
  "Set-Location '%ROOT%apps\dashboard'; $env:WORKFORCE_API_KEY='local-dev-key'; $env:WORKFORCE_API_BASE_URL='http://127.0.0.1:8000'; npm.cmd run dev"

rem --- open the browser after a short warm-up --------------------------------
start "" powershell -Command ^
  "Start-Sleep -Seconds 6; Start-Process 'http://localhost:3000'"

rem --- API runs in THIS window (Ctrl+C stops it; dashboard window separately) -
".venv\Scripts\python.exe" -m uvicorn services.api.main:app --host 127.0.0.1 --port 8000
if errorlevel 1 goto :fail
goto :eof

:fail
echo.
echo [error] Startup failed. See the messages above.
pause
