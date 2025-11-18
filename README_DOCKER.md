# Docker 部署指南

## 🐳 快速开始

### 1. 配置文件准备

编辑 `config.json`，填入您的小米账号信息。

### 2. 构建和运行

#### 方式一：使用 Compose（推荐）

```bash
# 启动服务
docker compose up -d

# 查看日志
docker compose logs -f

# 停止服务
docker compose down
```

#### 方式二：使用 Docker 命令

```bash
# 构建镜像
docker build -t xiaomi-doorbell .

# 运行容器
docker run -d \
  --name xiaomi-doorbell \
  --restart unless-stopped \
  -v $(pwd)/config.json:/app/config.json:ro \
  -v $(pwd)/video:/app/video \
  -v $(pwd)/data.json:/app/data.json \
  -v $(pwd)/auth_cache.json:/app/auth_cache.json \
  xiaomi-doorbell

# 查看日志
docker logs -f xiaomi-doorbell
```

## 🔧 配置说明

### FFmpeg 路径

FFmpeg 路径配置保持原样即可，系统会自动处理：

- **Docker 环境**：自动使用系统 PATH 中的 `ffmpeg`
- **本地环境**：使用配置文件中的路径

### 目录挂载

- `config.json`: 配置文件（只读）
- `video/`: 视频保存目录
- `data.json`: 事件记录文件
- `auth_cache.json`: 登录缓存文件

## 🚨 故障排除

### FFmpeg 相关错误

```bash
# 检查容器中是否安装了 FFmpeg
docker exec xiaomi-doorbell ffmpeg -version
```

### 查看日志

```bash
# Compose 方式
docker compose logs -f

# Docker 命令方式
docker logs -f xiaomi-doorbell
```

## 📋 验证

```bash
# 检查容器状态
docker ps

# 检查日志输出
docker compose logs --tail 50
```