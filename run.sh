#!/bin/bash

# 一键运行脚本

echo "=================================="
echo "办公文档智能分类与检索系统运行脚本"
echo "=================================="

# 定义目录路径
PROJECT_ROOT=$(pwd)
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
STATIC_DIR="$FRONTEND_DIR/dist"

# 获取局域网IP
LAN_IP=$(hostname -I | awk '{print $1}')

# 启动前端静态服务
echo "启动前端静态服务..."
cd "$PROJECT_ROOT"
python3 -m http.server 6017 --directory "$STATIC_DIR" &
FRONTEND_PID=$!
echo "前端静态服务已启动，PID: $FRONTEND_PID"

# 启动后端服务
echo "启动后端服务..."
cd "$BACKEND_DIR"
echo "安装依赖..."
pip install -r requirements.txt --quiet
pip install python-multipart --quiet
echo "依赖安装完成"
echo "启动后端服务..."
PYTHONPATH=. python main_new.py &
BACKEND_PID=$!
echo "后端服务已启动，PID: $BACKEND_PID"

echo "=================================="
echo "系统已成功运行！"
echo "=================================="
echo "局域网内设备可通过以下URL访问："
echo "前端页面：http://$LAN_IP:6017"
echo "后端API：http://$LAN_IP:6010"
echo ""
echo "确保设备与服务器在同一局域网内"
echo "=================================="
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待用户输入
wait

# 停止服务
echo "停止服务..."
kill $FRONTEND_PID $BACKEND_PID

echo "服务已停止"
