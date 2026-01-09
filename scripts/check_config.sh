#!/bin/bash

# 配置检查脚本
echo "=== 系统配置检查 ==="

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "项目目录: $SCRIPT_DIR"
echo ""

# 检查Redis配置
echo "1. 检查Redis服务..."
if redis-cli ping > /dev/null 2>&1; then
    echo "   ✅ Redis服务正常 (端口: 6379)"
else
    echo "   ❌ Redis服务未运行"
    echo "   启动命令: redis-server"
fi

echo ""

# 检查MySQL配置
echo "2. 检查MySQL服务..."
if mysqladmin ping -h127.0.0.1 -P3306 -utest -ptest > /dev/null 2>&1; then
    echo "   ✅ MySQL服务正常 (端口: 3306)"
    
    # 检查数据库
    if mysql -h127.0.0.1 -P3306 -utest -ptest -e "USE t11;" > /dev/null 2>&1; then
        echo "   ✅ 数据库 t11 存在"
    else
        echo "   ❌ 数据库 t11 不存在"
        echo "   请运行: mysql -h127.0.0.1 -P3306 -utest -ptest < db.sql"
    fi
else
    echo "   ❌ MySQL连接失败"
    echo "   请检查MySQL服务是否运行，用户名密码是否正确"
fi

echo ""

# 检查Python依赖
echo "3. 检查Python环境..."
if python --version > /dev/null 2>&1; then
    echo "   ✅ Python已安装: $(python --version 2>&1)"
else
    echo "   ❌ Python未安装"
fi

if pip --version > /dev/null 2>&1; then
    echo "   ✅ pip已安装: $(pip --version 2>&1 | cut -d' ' -f1-2)"
else
    echo "   ❌ pip未安装"
fi

echo ""

# 检查关键文件
echo "4. 检查项目文件..."
files=("app.py" "requirements.txt" "file_process/__init__.py" "config/db_config.py" "config/app_config.py")
for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "   ✅ $file 存在"
    else
        echo "   ❌ $file 不存在"
    fi
done

echo ""

# 检查配置文件内容
echo "5. 检查配置文件..."
if [ -f "config/app_config.py" ]; then
    echo "   ✅ 统一配置文件存在"
    
    # 检查配置是否正确
    if python -c "
import sys
import os
# 确保导入根目录的config，而不是file_process下的config
parent_dir = os.path.dirname(os.getcwd())
sys.path.insert(0, parent_dir)
from config.app_config import Config
print('   MySQL URI:', Config.get_mysql_uri())
print('   Redis URI:', Config.get_redis_uri())
" 2>/dev/null; then
        echo "   ✅ 配置文件格式正确"
    else
        echo "   ❌ 配置文件格式错误"
    fi
else
    echo "   ❌ 统一配置文件不存在"
fi

echo ""

# 检查依赖包
echo "6. 检查Python依赖包..."
packages=("flask" "celery" "redis" "pymysql")
for package in "${packages[@]}"; do
    if python -c "import $package" > /dev/null 2>&1; then
        echo "   ✅ $package 已安装"
    else
        echo "   ❌ $package 未安装"
    fi
done

echo ""
echo "=== 检查完成 ==="
echo ""
echo "如果所有检查都通过，可以运行: ./start_system.sh"
echo "如果有依赖缺失，请运行: pip install -r requirements.txt"