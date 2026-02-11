#!/bin/bash

# 一键部署和运行脚本

echo "=================================="
echo "办公文档智能分类与检索系统部署脚本"
echo "=================================="

# 定义目录路径
PROJECT_ROOT=$(pwd)
FRONTEND_DIR="$PROJECT_ROOT/../frontend"
BACKEND_DIR="$PROJECT_ROOT/../backend"
DOC_DIR="$PROJECT_ROOT/../doc"
MODEL_DIR="$PROJECT_ROOT/../model"
STATIC_DIR="$PROJECT_ROOT/../static"

# 创建必要的目录
echo "创建必要的目录..."
mkdir -p "$DOC_DIR" "$MODEL_DIR" "$STATIC_DIR"

# 安装后端依赖
echo "安装后端依赖..."
cd "$BACKEND_DIR"
pip install -r requirements.txt

# 安装前端依赖
echo "安装前端依赖..."
cd "$FRONTEND_DIR"
npm config set registry https://registry.npmmirror.com
npm cache clean --force
rm -rf node_modules package-lock.json
npm install

# 构建前端项目
echo "构建前端项目..."
npm run build

# 复制前端构建产物到static目录
echo "复制前端构建产物到static目录..."
rm -rf "$STATIC_DIR"/*
cp -r "$FRONTEND_DIR/dist"/* "$STATIC_DIR/"

# 启动后端服务
echo "启动后端服务..."
cd "$BACKEND_DIR"

# 获取局域网IP
LAN_IP=$(hostname -I | awk '{print $1}')

echo "=================================="
echo "部署完成！"
echo "=================================="
echo "系统已成功运行，局域网内设备可通过以下URL访问："
echo "前端页面：http://$LAN_IP:6006"
echo "后端API：http://$LAN_IP:6008"
echo ""
echo "确保设备与服务器在同一局域网内"
echo "=================================="

# 启动后端服务
python main.py
