#!/bin/bash
# 启动 file-parser 服务
# 用法: ./start.sh [port]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d ".venv" ]; then
    echo "虚拟环境不存在，请先创建并安装依赖："
    echo "  python3.10 -m venv .venv"
    echo "  source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

source .venv/bin/activate

PORT="${1:-8000}"
echo "Starting file-parser on port $PORT..."
uvicorn main:app --host 0.0.0.0 --port "$PORT"
