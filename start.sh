#!/bin/bash
# 闲鱼 AI 助手 — 启动脚本
set -e

# 确保目录存在
mkdir -p /app/data /app/logs

echo "=== 闲鱼 AI 助手 v0.4 ==="
echo "启动时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "日志目录: /app/logs/"
echo "================================================"

exec python3 -u -m uvicorn src.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level info \
    --proxy-headers \
    --forwarded-allow-ips '*'
