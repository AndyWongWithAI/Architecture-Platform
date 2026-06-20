# arch-platform backend — 架构平台后端镜像
# 构建上下文:项目根目录(包含 backend/ + docs/components/)
#
# 构建:  docker build -t arch-platform:0.1.0 .
# 运行:  docker compose up -d

FROM python:3.12-slim

LABEL maintainer="andywong"
LABEL description="Architecture Platform backend — 组件登记 / 复用 / 反馈"
LABEL version="0.1.0"

# 工作目录
WORKDIR /app

# 系统依赖:tzdata 让日志时间戳带时区,ca-certificates 走 HTTPS 拉镜像时用
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖(先 copy pyproject 充分利用 Docker layer cache)
COPY backend/pyproject.toml ./backend/
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir ./backend

# 应用代码 + 种子数据
COPY backend/app/ ./app/
COPY backend/scripts/ ./scripts/
COPY docs/components/ /app/docs/components/

# 数据 / 备份目录
RUN mkdir -p /app/data /app/backups

# 环境变量默认值
ENV ARCH_DB_PATH=/app/data/arch.db
ENV ARCH_PLATFORM_API_KEY=""
ENV TZ=Asia/Shanghai
ENV PYTHONUNBUFFERED=1

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/healthz', timeout=3).read()" \
    || exit 1

# 暴露端口
EXPOSE 8088

# 启动命令(SQLite + 单 worker;后续 PostgreSQL 切换改多 worker)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]