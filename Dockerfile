FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装Python包
COPY requirements.txt ./
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple && \
    pip config set install.trusted-host mirrors.aliyun.com && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY main.py ./
COPY src/ ./src/

# 创建必要的目录并设置权限
RUN mkdir -p ./video ./config && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# 设置环境变量
ENV DOCKER_ENV=true

# 切换到非root用户
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

CMD ["python","main.py"]