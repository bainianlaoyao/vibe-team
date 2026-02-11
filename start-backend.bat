@echo off
chcp 65001 >nul
echo ====================================
echo   BeeBeeBrain 后端启动脚本
echo ====================================

cd /d "%~dp0backend"

:: 设置 CORS 允许的前端地址 (现在使用 allow_origin_regex 自动匹配本地端口)
set APP_ENV=development
set DEBUG=true
set LOG_FORMAT=console

:: 项目目录配置 (数据库存放在此处)
if not defined PROJECT_ROOT set PROJECT_ROOT=../play_ground

echo.
echo [配置信息]
echo   项目目录: %PROJECT_ROOT%
echo   数据库: %PROJECT_ROOT%/.beebeebrain/beebeebrain.db
echo   API地址: http://127.0.0.1:8000
echo   Windows: 使用 ProactorEventLoop 支持 asyncio subprocess
echo.

:: 使用自定义启动脚本解决 Windows asyncio subprocess 问题
uv run python run_server.py
