#!/bin/bash

set -euo pipefail

# 文档处理系统启动脚本
echo "启动文档处理系统..."

# 获取项目根目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 设置环境变量（使用项目根目录）
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"
LOG_DIR="$PROJECT_ROOT/logs"
mkdir -p "$LOG_DIR"

# 使用 venv 的 Python（如果存在）
PYTHON="$PROJECT_ROOT/venv/bin/python"
if [ ! -f "$PYTHON" ]; then
    PYTHON="python"
    echo "⚠️  未找到 venv，使用系统 Python"
fi

# 检查Redis是否运行
echo "检查Redis服务..."
if ! redis-cli ping > /dev/null 2>&1; then
    echo "❌ Redis服务未运行，请先启动Redis服务"
    echo "启动命令: redis-server"
    exit 1
fi
echo "✅ Redis服务正常"

# 检查MySQL是否运行
echo "检查MySQL服务..."
if ! mysqladmin ping -h127.0.0.1 -P3306 -utest -ptest > /dev/null 2>&1; then
    echo "❌ MySQL服务未运行或连接失败，请检查数据库配置"
    exit 1
fi
echo "✅ MySQL服务正常"

# 启动Celery Worker (后台运行)
echo "启动Celery Worker..."
nohup $PYTHON -m celery -A file_process.models.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --pool=solo \
    --hostname=worker1@%h \
    > "$LOG_DIR/celery.log" 2>&1 &

CELERY_PID=$!
echo "Celery Worker已启动 (PID: $CELERY_PID)"

cleanup() {
    echo "停止Celery Worker..."
    kill "$CELERY_PID" 2>/dev/null || true
}
trap cleanup EXIT

# 等待Celery启动
sleep 3

# 启动Flask应用
echo "启动Flask应用..."
$PYTHON app.py

echo "系统已停止"
