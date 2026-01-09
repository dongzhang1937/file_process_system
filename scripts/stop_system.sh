#!/bin/bash

# 文档处理系统停止脚本
echo "停止文档处理系统..."

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 停止所有Celery Worker进程
echo "停止Celery Worker进程..."
pkill -f "celery.*worker" 2>/dev/null || true

# 停止Flask应用进程
echo "停止Flask应用进程..."
pkill -f "python.*app.py" 2>/dev/null || true

# 等待进程完全停止
sleep 2

# 检查是否还有相关进程
CELERY_COUNT=$(pgrep -f "celery.*worker" | wc -l)
FLASK_COUNT=$(pgrep -f "python.*app.py" | wc -l)

if [ $CELERY_COUNT -eq 0 ] && [ $FLASK_COUNT -eq 0 ]; then
    echo "✅ 系统已完全停止"
else
    echo "⚠️  仍有进程运行:"
    [ $CELERY_COUNT -gt 0 ] && echo "  - Celery Worker: $CELERY_COUNT 个进程"
    [ $FLASK_COUNT -gt 0 ] && echo "  - Flask应用: $FLASK_COUNT 个进程"
    echo "如需强制停止，请运行: pkill -9 -f 'celery|app.py'"
fi