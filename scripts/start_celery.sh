#!/bin/bash

# Celery Worker 启动脚本
echo "启动 Celery Worker..."

# 获取脚本所在目录的父目录（项目根目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 设置环境变量（使用项目根目录）
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# 检查是否已有 Celery 进程运行
if pgrep -f "celery.*file_process.models.celery_app" > /dev/null; then
    echo "检测到已有 Celery Worker 运行，正在停止..."
    pkill -f "celery.*file_process.models.celery_app"
    sleep 2
    echo "已停止旧进程"
fi

# 启动 Celery Worker
echo "正在启动 Celery Worker..."
LOG_FILE="$PROJECT_ROOT/celery.log"
python -m celery -A file_process.models.celery_app worker \
    --loglevel=info \
    --concurrency=1 \
    --pool=solo \
    --hostname=worker1@%h >> "$LOG_FILE" 2>&1 &

# 获取进程ID
CELERY_PID=$!
echo ""
echo "=========================================="
echo "Celery Worker 已启动 (PID: $CELERY_PID)"
echo "=========================================="
echo "日志文件: $LOG_FILE"
echo ""
echo "查看日志命令:"
echo "  tail -f $LOG_FILE"
echo ""
echo "停止 Worker:"
echo "  kill $CELERY_PID 或 pkill -f celery"
echo "=========================================="