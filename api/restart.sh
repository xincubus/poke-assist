#!/bin/bash
# 重启宝可梦 API 服务
cd ~/pokemon

# 杀掉旧进程
PID=$(pgrep -f "python api/main.py")
if [ -n "$PID" ]; then
    kill $PID
    echo "已停止旧进程 (PID: $PID)"
    sleep 1
else
    echo "没有运行中的进程"
fi

# 激活虚拟环境并启动
source .venv/bin/activate
nohup python api/main.py > api.log 2>&1 &
echo "服务已启动 (PID: $!)"
echo "日志: tail -f ~/pokemon/api.log"
