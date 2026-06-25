# ── Job Market Analytics ──
# Multi-service Docker setup: Streamlit + FastAPI + Nginx

FROM python:3.11-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI 服务依赖
RUN pip install --no-cache-dir fastapi uvicorn

# 应用代码
COPY . .

# 数据目录（挂载点）
RUN mkdir -p /app/data/processed /app/data/raw /app/reports /app/logs

EXPOSE 8501 8502

# 默认启动由 docker-compose command 覆盖
CMD ["echo", "Use docker-compose.yml to start services"]
