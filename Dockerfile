# 闲鱼 AI 助手 — 多阶段 Docker 构建
# Stage 1: 依赖安装
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: 运行时（最小镜像）
FROM python:3.11-slim
WORKDIR /app

# 非 root 用户
RUN useradd --create-home --shell /bin/bash xianyu && \
    chown -R xianyu:xianyu /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# 应用代码
COPY --chown=xianyu:xianyu src/ ./src/
COPY --chown=xianyu:xianyu frontend/ ./frontend/
COPY --chown=xianyu:xianyu start.sh ./

RUN chmod +x start.sh

USER xianyu
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python3 -c "import httpx; r=httpx.get('http://localhost:8000/api/health'); assert r.json()['status']=='ok'" || exit 1

CMD ["./start.sh"]
