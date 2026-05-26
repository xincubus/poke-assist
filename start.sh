#!/bin/bash
cd "$(dirname "$0")"

echo "正在拉取最新代码..."

# 备份 .env 文件（防止 git 操作误删）
[ -f api/.env ] && cp api/.env /tmp/.env.bak && echo "已备份 api/.env"

OLD_HEAD=$(git rev-parse HEAD)
git fetch origin
git checkout -- .
git clean -fd -e api/.env
git reset --hard origin/master
git lfs pull

# git 操作完成后立即恢复 .env
if [ -f /tmp/.env.bak ]; then
    cp /tmp/.env.bak api/.env
    rm /tmp/.env.bak
    echo "已恢复 api/.env"
fi
NEW_HEAD=$(git rev-parse HEAD)
if [ "$OLD_HEAD" != "$NEW_HEAD" ]; then
    echo "更新的提交："
    git log --oneline "$OLD_HEAD".."$NEW_HEAD"
else
    echo "已是最新，无新提交"
fi

echo "正在关闭已有服务..."
pkill -f "uvicorn api.main:app" 2>/dev/null
pkill -f "crawl_champions_usage" 2>/dev/null
sleep 1

source .venv/bin/activate

echo "启动宝可梦助手 API..."
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > api.log 2>&1 &
echo "服务已启动，PID: $!"
echo "日志：tail -f $(pwd)/api.log"

# HOME使用率爬虫定时任务（每天凌晨2点）
nohup bash -c '
while true; do
    NOW_H=$(date +%H)
    NOW_M=$(date +%M)
    TARGET=120
    NOW_MIN=$((10#$NOW_H * 60 + 10#$NOW_M))
    if [ $NOW_MIN -lt $TARGET ]; then
        SLEEP=$((($TARGET - $NOW_MIN) * 60))
    else
        SLEEP=$((((1440 - $NOW_MIN + $TARGET)) * 60))
    fi
    echo "[$(date)] 下次爬取：$((SLEEP / 3600))小时$((SLEEP % 3600 / 60))分钟后"
    sleep $SLEEP
    echo "[$(date)] 开始爬取HOME使用率数据..."
    cd '"'"$(pwd)/home/champions"'"' && '"'"$(pwd)/.venv/bin/python"'"' crawl_champions_usage.py >> crawl.log 2>&1
    echo "[$(date)] 爬取完成"
done
' > /dev/null 2>&1 &
echo "HOME爬虫定时任务已启动，每天凌晨2:00执行"
