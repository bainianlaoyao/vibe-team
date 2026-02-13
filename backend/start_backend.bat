@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
call "%SCRIPT_DIR%..\start-backend.bat" %*
exit /b %ERRORLEVEL%
