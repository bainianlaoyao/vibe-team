@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%.") do set "REPO_ROOT=%%~fI"
set "BACKEND_DIR=%REPO_ROOT%\backend"

if not exist "%BACKEND_DIR%\app\main.py" (
  echo [ERROR] backend app not found under "%BACKEND_DIR%"
  exit /b 1
)

pushd "%BACKEND_DIR%" || exit /b 1

if /I "%~1"=="--print-cwd" (
  echo %CD%
  popd
  exit /b 0
)

set "APP_ENV=development"
set "PROJECT_ROOT=%REPO_ROOT%\play_ground"
set "CORS_ALLOW_ORIGINS=*"
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
set "EXIT_CODE=%ERRORLEVEL%"

popd
exit /b %EXIT_CODE%
