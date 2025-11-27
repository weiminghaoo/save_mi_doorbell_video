#!/bin/bash

# 初始化配置文件脚本
echo "正在初始化小米门铃配置..."

# 创建config目录
mkdir -p config

# 如果配置文件不存在，创建默认配置
if [ ! -f "config/config.json" ]; then
    cat > config/config.json << 'EOF'
{
    "username": "",
    "password": "",
    "save_path": "./video",
    "ffmpeg": "/opt/homebrew/bin/ffmpeg",
    "schedule_minutes": 10,
    "merge": true,
    "use_qr_login": true,
    "cleanup_ts_files": true
}
EOF
    echo "已创建默认配置文件: config/config.json"
    echo "请编辑此文件并填入您的米家账号信息"
else
    echo "配置文件已存在: config/config.json"
fi

# 创建video目录
mkdir -p video

echo "初始化完成！"
echo "请确保已编辑 config/config.json 文件填入账号信息后运行 docker-compose up"