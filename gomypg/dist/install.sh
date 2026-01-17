#!/bin/bash

# mygo 安装脚本
# 自动检测平台并安装对应的二进制文件

set -e

VERSION="1.0.0"
INSTALL_DIR="/usr/local/bin"
BINARY_NAME="mygo"

# 检测操作系统和架构
detect_platform() {
    local os=$(uname -s | tr '[:upper:]' '[:lower:]')
    local arch=$(uname -m)
    
    case "$os" in
        linux*)
            OS="linux"
            ;;
        darwin*)
            OS="darwin"
            ;;
        mingw*|msys*|cygwin*)
            OS="windows"
            ;;
        *)
            echo "错误: 不支持的操作系统 $os"
            exit 1
            ;;
    esac
    
    case "$arch" in
        x86_64|amd64)
            ARCH="amd64"
            ;;
        arm64|aarch64)
            ARCH="arm64"
            ;;
        *)
            echo "错误: 不支持的架构 $arch"
            exit 1
            ;;
    esac
    
    if [ "$OS" = "windows" ]; then
        BINARY_EXT=".exe"
        ARCHIVE_NAME="${BINARY_NAME}-${VERSION}-${OS}-${ARCH}.tar.gz"
        BINARY_FILE="${BINARY_NAME}-${OS}-${ARCH}${BINARY_EXT}"
    else
        BINARY_EXT=""
        ARCHIVE_NAME="${BINARY_NAME}-${VERSION}-${OS}-${ARCH}.tar.gz"
        BINARY_FILE="${BINARY_NAME}-${OS}-${ARCH}"
    fi
    
    echo "检测到平台: $OS-$ARCH"
}

# 安装函数
install_mygo() {
    if [ ! -f "$ARCHIVE_NAME" ]; then
        echo "错误: 找不到文件 $ARCHIVE_NAME"
        echo "请确保在包含发布文件的目录中运行此脚本"
        exit 1
    fi
    
    echo "正在解压 $ARCHIVE_NAME..."
    tar -xzf "$ARCHIVE_NAME"
    
    if [ ! -f "$BINARY_FILE" ]; then
        echo "错误: 解压后找不到二进制文件 $BINARY_FILE"
        exit 1
    fi
    
    # 检查是否有写权限
    if [ -w "$INSTALL_DIR" ]; then
        echo "正在安装到 $INSTALL_DIR/$BINARY_NAME..."
        cp "$BINARY_FILE" "$INSTALL_DIR/$BINARY_NAME"
        chmod +x "$INSTALL_DIR/$BINARY_NAME"
        echo "安装成功！"
    else
        echo "需要管理员权限安装到 $INSTALL_DIR"
        echo "正在使用 sudo 安装..."
        sudo cp "$BINARY_FILE" "$INSTALL_DIR/$BINARY_NAME"
        sudo chmod +x "$INSTALL_DIR/$BINARY_NAME"
        echo "安装成功！"
    fi
    
    # 清理临时文件
    rm -f "$BINARY_FILE"
    
    echo ""
    echo "安装完成！现在可以使用 'mygo' 命令。"
    echo ""
    echo "🎯 使用示例:"
    echo "  # 连接 PostgreSQL (自动使用默认数据库)"
    echo "  mygo -u postgres -H 127.0.0.1 -t pg -p your_password"
    echo ""
    echo "  # 连接 MySQL (自动使用默认数据库)"
    echo "  mygo -u root -H 127.0.0.1 -t mysql -p your_password"
    echo ""
    echo "  # 查看帮助"
    echo "  mygo --help"
    echo ""
    echo "🆕 新功能:"
    echo "  - show --help           # 查看所有 SHOW 命令"
    echo "  - show create --help    # 查看 CREATE 语法"
    echo "  - SHOW CREATE DATABASE db_name;  # 显示数据库创建语句"
}

# 主函数
main() {
    echo "mygo $VERSION 安装程序"
    echo "======================"
    echo ""
    
    detect_platform
    install_mygo
}

# 运行主函数
main "$@"