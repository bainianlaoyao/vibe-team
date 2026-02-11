#!/bin/bash
echo "===================================="
echo "  BeeBeeBrain 后端启动脚本"
echo "===================================="

cd "$(dirname "$0")/backend"

# 开发环境配置 (CORS 现在使用 allow_origin_regex 自动匹配本地端口)
export APP_ENV=development
export DEBUG=true
export LOG_FORMAT=console

# 项目目录配置 (数据库存放在此处)
export PROJECT_ROOT="${PROJECT_ROOT:-../play_ground}"

echo ""
echo "[配置信息]"
echo "  项目目录: $PROJECT_ROOT"
echo "  数据库: $PROJECT_ROOT/.beebeebrain/beebeebrain.db"
echo "  API地址: http://127.0.0.1:8000"
echo ""

# 检测操作系统，Windows 使用自定义启动脚本
if [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "  Windows: 使用 ProactorEventLoop 支持 asyncio subprocess"
    uv run python run_server.py
else
    # Linux/macOS 直接使用 uvicorn
    uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
fi
