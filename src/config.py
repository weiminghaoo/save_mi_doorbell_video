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


def from_file(path='config/config.json') -> Config:
    with open(path, 'r') as f:
        config = json.load(f)
        return Config(**config)
