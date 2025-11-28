FROM python:3.11-slim

# 完全替换 apt 源为清华源
RUN echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye main contrib non-free" > /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bullseye-updates main contrib non-free" >> /etc/apt/sources.list && \
    echo "deb https://mirrors.tuna.tsinghua.edu.cn/debian-security/ bullseye-security main contrib non-free" >> /etc/apt/sources.list && \
    # 删除可能存在的其他源配置文件
    rm -f /etc/apt/sources.list.d/* && \
    # 禁用检查软件包有效期
    echo "Acquire::Check-Valid-Until false;" > /etc/apt/apt.conf.d/99no-check-valid-until

# 安装系统依赖 - 先尝试安装更基础的包解决依赖问题
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
       libavformat58 libavcodec58 libavutil56 libswscale5 libavfilter7 \
    && \
    apt-get install -y --no-install-recommends ffmpeg \
    && \
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