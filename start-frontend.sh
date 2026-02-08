#!/bin/bash
echo "===================================="
echo "  BeeBeeBrain 前端启动脚本"
echo "===================================="

cd "$(dirname "$0")/frontend"

echo ""
echo "[配置信息]"
echo "  开发服务器: http://localhost:5173"
echo "  后端API: http://127.0.0.1:8000/api/v1"
echo ""

npm run dev
