import json
import os
from typing import NamedTuple


class Config(NamedTuple):
    username: str
    password: str
    save_path: str
    schedule_minutes: int
    ffmpeg: str
    merge: bool
    use_qr_login: bool
    cleanup_ts_files: bool

    def get_ffmpeg_path(self) -> str:
        """获取ffmpeg路径"""
        # 在Docker环境中直接使用系统ffmpeg
        if os.getenv('DOCKER_ENV'):
            return 'ffmpeg'

        # 本地环境使用配置的路径
        return self.ffmpeg


def from_file(path='/app/config/config.json') -> Config:
    # 优先尝试从环境变量读取配置
    if os.getenv('MI_USERNAME') and os.getenv('MI_PASSWORD'):
        print("使用环境变量配置")
        return Config(
            username=os.getenv('MI_USERNAME', ''),
            password=os.getenv('MI_PASSWORD', ''),
            save_path=os.getenv('MI_SAVE_PATH', '/app/video'),
            ffmpeg=os.getenv('MI_FFMPEG', '/opt/homebrew/bin/ffmpeg'),
            schedule_minutes=int(os.getenv('MI_SCHEDULE_MINUTES', '10')),
            merge=True,
            use_qr_login=True,
            cleanup_ts_files=True
        )

    # 如果配置文件不存在，创建默认配置文件
    if not os.path.exists(path):
        default_config = {
            "username": "",
            "password": "",
            "save_path": "./video",
            "ffmpeg": "/opt/homebrew/bin/ffmpeg",
            "schedule_minutes": 10,
            "merge": True,
            "use_qr_login": True,
            "cleanup_ts_files": True
        }

        # 确保配置目录存在
        config_dir = os.path.dirname(path)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        # 创建默认配置文件
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=4)

        print(f"已自动创建配置文件: {path}")
        print("请编辑配置文件并填入您的米家账号信息")

    with open(path, 'r') as f:
        config = json.load(f)
        return Config(**config)
