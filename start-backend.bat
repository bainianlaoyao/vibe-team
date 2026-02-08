@echo off
chcp 65001 >nul
echo ====================================
echo   BeeBeeBrain 后端启动脚本
echo ====================================

cd /d "%~dp0backend"

:: 设置 CORS 允许的前端地址
set CORS_ALLOW_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:5175,http://127.0.0.1:5175

:: 开发环境配置
set APP_ENV=development
set DEBUG=true
set LOG_FORMAT=console

echo.
echo [配置信息]
echo   数据库: backend/beebeebrain.db
echo   API地址: http://127.0.0.1:8000
echo   CORS: %CORS_ALLOW_ORIGINS%
echo.

uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
