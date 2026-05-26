#!/bin/bash
# API 服务启动脚本

echo "正在启动宝可梦助手 API 服务..."
echo ""

cd "$(dirname "$0")"

# 检查依赖
echo "检查依赖..."
python -c "import fastapi, uvicorn, pydantic" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ 缺少依赖，正在安装..."
    pip install -r "$(dirname "$0")/../requirements.txt"
fi

echo "✓ 依赖检查完成"
echo ""

# 启动服务
echo "启动服务在 http://localhost:8000"
echo "API 文档: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

python main.py
