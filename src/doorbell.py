import json
from urllib.parse import urlencode
import logging
import time
from datetime import datetime
import locale
import binascii
import os

import requests
import subprocess
from Crypto.Cipher import AES
from typing import NamedTuple, List

from src.xiaomi_cloud import MiotCloud

_LOGGER = logging.getLogger(__name__)


def generate_unique_filename(base_path, extension=""):
    """生成唯一的文件名，如果文件已存在则添加序号"""
    if not base_path:
        raise ValueError("base_path 不能为空")

    if not extension.startswith('.'):
        extension = '.' + extension if extension else ''

    original_path = base_path + extension
    counter = 1

    # 如果原始文件名不存在，直接返回
    if not os.path.exists(original_path):
        return original_path

    # 文件已存在，添加序号
    while True:
        new_path = f"{base_path}_{counter}{extension}"
        if not os.path.exists(new_path):
            return new_path
        counter += 1


class DoorbellEvent(NamedTuple):
    eventTime: int
    fileId: str
    eventType: str

    def date_time_fmt(self):
        t = datetime.fromtimestamp(float(self.eventTime) / 1000)
        return t.strftime("%Y-%m-%d %H:%M:%S")

    def short_time_fmt(self):
        t = datetime.fromtimestamp(float(self.eventTime) / 1000)
        return t.strftime("%H%M%S")

    def shot_date_fmt(self):
        t = datetime.fromtimestamp(float(self.eventTime) / 1000)
        return t.strftime("%Y%m%d")

    def shot_date_hierarchical_fmt(self):
        """生成年/月/日格式的日期，用于目录层级结构"""
        t = datetime.fromtimestamp(float(self.eventTime) / 1000)
        return t.strftime("%Y/%m/%d")

    def event_type_name(self):
        if self.eventType == "Pass":
            return "有人在门前经过"
        elif self.eventType == "Pass:Stay":
            return "有人在门停留"
        elif self.eventType == "Bell":
            return "有人按门铃"
        elif self.eventType == "Pass:Bell":
            return "有人按门铃"
        else:
            return self.eventType

    def event_desc(self):
        return "%s %s" % (self.date_time_fmt(), self.event_type_name())

    def generate_unique_dirname(self):
        """生成唯一的目录名，包含时间、事件类型和文件ID"""
        time_str = self.short_time_fmt()
        # 转换事件类型为简短标识
        event_type_map = {
            "Pass": "pass",
            "Stay": "stay",
            "Pass:Stay": "stay",
            "Bell": "bell",
            "Pass:Bell": "bell"
        }
        event_type_short = event_type_map.get(self.eventType, "unknown")

        # 使用fileId的后6位作为唯一标识
        file_id_short = self.fileId[-6:] if len(self.fileId) >= 6 else self.fileId

        # 组合: 时间_类型_唯一ID
        return f"{time_str}_{event_type_short}_{file_id_short}"


class MiDoorbell:

    def __init__(self, xiaomi_cloud: MiotCloud, name, did, model):
        self.xiaomi_cloud = xiaomi_cloud
        self.name = name
        self._state_attrs = {}
        self.miot_did = did
        self.model = model

    def get_event_list(
        self, start_time=None, end_time=None, limit=10
    ) -> List[DoorbellEvent]:
        mic = self.xiaomi_cloud
        lag = locale.getlocale()[0]
        if start_time:
            stm = start_time
        else:
            stm = int(time.time() - 86400 * 1) * 1000

        if end_time:
            etm = end_time
        else:
            etm = int(time.time() * 1000 + 999)

        api = mic.get_api_by_host(
            "business.smartcamera.api.io.mi.com", "common/app/get/eventlist"
        )
        rqd = {
            "did": self.miot_did,
            "model": self.model,
            "doorBell": True,
            "eventType": "Default",
            "needMerge": True,
            "sortType": "DESC",
            "region": str(mic.default_server).upper(),
            "language": lag,
            "beginTime": stm,
            "endTime": etm,
            "limit": limit,
        }

        all_list = []
        is_continue = True
        next_time = etm

        while is_continue:
            rqd["endTime"] = next_time

            rdt = mic.request_miot_api(api, rqd, method="GET", crypt=True) or {}
            data = rdt.get("data", {})
            is_continue = data["isContinue"]
            next_time = data["nextTime"]

            rls = data.get("thirdPartPlayUnits") or []

            for item in rls:
                all_list.append(
                    DoorbellEvent(
                        eventTime=int(item["createTime"]),
                        fileId=item["fileId"],
                        eventType=item["eventType"],
                    )
                )

        return all_list

    def download_video(self, event: DoorbellEvent, save_path, merge=False, ffmpeg=None, cleanup_ts_files=True, device_name=None):
        # 验证输入参数
        _LOGGER.debug(f"download_video 调用参数: save_path='{save_path}', merge={merge}, ffmpeg='{ffmpeg}', cleanup_ts_files={cleanup_ts_files}', device_name='{device_name}'")

        if not save_path:
            raise ValueError("save_path 不能为空")
        if not event:
            raise ValueError("event 不能为空")

        m3u8_url = self.get_video_m3u8_url(event)
        resp = requests.get(m3u8_url)
        lines = resp.content.splitlines()
        video_cnt = 0
        key = None
        iv = None

        # 生成基础路径 - 使用设备名称目录和年/月/日格式
        date_str = event.shot_date_hierarchical_fmt()
        unique_dirname = event.generate_unique_dirname()

        # 清理设备名称，移除不安全的字符
        safe_device_name = self._sanitize_device_name(device_name) if device_name else "unknown_device"

        _LOGGER.debug(f"事件信息: date_str='{date_str}', unique_dirname='{unique_dirname}', fileId='{event.fileId}', eventType='{event.eventType}', device_name='{device_name}', safe_device_name='{safe_device_name}'")

        if not date_str or not unique_dirname:
            raise ValueError("事件的日期或唯一目录名为空")

        # 新的路径结构: save_path/设备名/年/月/日/唯一目录
        base_video_path = os.path.join(save_path, safe_device_name, date_str, unique_dirname)
        _LOGGER.debug(f"基础视频路径: '{base_video_path}'")

        # 检查并生成唯一的视频文件路径
        final_video_path = generate_unique_filename(base_video_path)
        _LOGGER.debug(f"最终视频路径: '{final_video_path}'")

        # 确保路径有效
        if not final_video_path:
            raise ValueError("生成的视频路径为空")

        # 对于目录路径，直接使用完整路径
        # 因为这是视频目录，不是文件
        final_path_without_ext = final_video_path
        _LOGGER.debug(f"最终路径无扩展名: '{final_path_without_ext}'")

        ts_path = os.path.join(final_path_without_ext, "ts")
        _LOGGER.debug(f"TS文件路径: '{ts_path}'")

        # 验证路径
        if not final_path_without_ext:
            raise ValueError("final_path_without_ext 为空")
        if not ts_path:
            raise ValueError("ts_path 为空")

        os.makedirs(final_path_without_ext, exist_ok=True)
        os.makedirs(ts_path, exist_ok=True)

        # 确保目录创建成功
        if not os.path.exists(ts_path):
            raise OSError(f"无法创建TS目录: {ts_path}")

        # 保存文件的同时，生成文件清单到filelist
        filelist_path = os.path.join(ts_path, "filelist")
        _LOGGER.debug(f"Filelist路径: '{filelist_path}'")

        with open(filelist_path, "w") as filelist:
            for line in lines:
                line = line.decode("utf-8")
                # 解析密钥信息
                if line.startswith("#EXT-X-KEY"):
                    start = line.index('URI="')
                    url = line[start : line.index('"', start + 10)][5:]
                    key = requests.get(url).content
                    iv = binascii.unhexlify(line[line.index("IV=") :][5:])

                # 解析视频URL并下载
                if line.startswith("http"):
                    r = requests.get(line)
                    video_cnt += 1
                    crypto = AES.new(key, AES.MODE_CBC, iv)
                    filename = str(video_cnt) + ".ts"

                    ts_file_path = os.path.join(ts_path, filename)
                    with open(ts_file_path, "wb") as f:
                        f.write(crypto.decrypt(r.content))

                    # 添加文件名和列表中，方便ffmpeg做视频合并
                    filelist.writelines("file '" + filename + "'\n")

        if video_cnt > 0 and merge and ffmpeg:
            # 生成包含事件类型的MP4文件名
            base_mp4_name = event.generate_unique_dirname()  # 使用目录名作为MP4文件名
            base_mp4_path = os.path.join(final_path_without_ext, base_mp4_name)
            unique_mp4_path = generate_unique_filename(base_mp4_path, "mp4")
            unique_mp4_name = os.path.basename(unique_mp4_path)  # 只获取文件名部分

            if not unique_mp4_name:
                raise ValueError("生成的MP4文件名为空")

            # 使用ffmpeg进行文件合并，输出到日期目录（上上级目录）
            cmd = (
                ffmpeg
                + " -f concat -i filelist -y -c:v libx264 -c:a aac ../../"
                + unique_mp4_name
            ).split(" ")

            _LOGGER.debug(f"FFmpeg命令: {' '.join(cmd)}")
            _LOGGER.debug(f"工作目录: {ts_path}")

            try:
                subprocess.check_output(cmd, cwd=ts_path, stderr=subprocess.STDOUT)
                _LOGGER.debug("FFmpeg执行成功")
            except subprocess.CalledProcessError as e:
                error_msg = f"FFmpeg执行失败: {e.output.decode() if e.output else '无错误输出'}"
                _LOGGER.error(error_msg)
                raise OSError(error_msg)

            # MP4文件已生成在日期目录（事件文件夹的父目录）
            date_dir = os.path.dirname(final_path_without_ext)
            final_mp4_path = os.path.join(date_dir, unique_mp4_name)

            _LOGGER.debug(f"预期MP4路径: {final_mp4_path}")
            _LOGGER.debug(f"日期目录内容: {os.listdir(date_dir) if os.path.exists(date_dir) else '目录不存在'}")

            # 验证MP4文件是否成功生成
            if not os.path.exists(final_mp4_path):
                raise OSError(f"MP4文件生成失败: {final_mp4_path}")

            _LOGGER.info(f"MP4文件已生成: {final_mp4_path}")

            # 根据配置决定是否清理事件文件夹
            if cleanup_ts_files:
                self._cleanup_event_folder(final_path_without_ext)
            else:
                _LOGGER.debug(f"事件文件夹清理已禁用，保留文件夹: {final_path_without_ext}")

            # 返回最终的MP4文件路径
            return final_mp4_path

        return final_path_without_ext

    def _sanitize_device_name(self, device_name):
        """清理设备名称，移除不安全的文件系统字符"""
        if not device_name:
            return "unknown_device"

        # 替换不安全的字符
        unsafe_chars = '<>:"/\\|?*'
        safe_name = device_name

        for char in unsafe_chars:
            safe_name = safe_name.replace(char, '_')

        # 移除开头和结尾的空格和点
        safe_name = safe_name.strip(' .')

        # 确保不为空
        if not safe_name:
            return "unknown_device"

        # 限制长度
        if len(safe_name) > 50:
            safe_name = safe_name[:50]

        return safe_name

    def _cleanup_ts_files(self, ts_path, video_dir_path):
        """清理TS文件和临时目录"""
        try:
            if not os.path.exists(ts_path):
                _LOGGER.debug(f"TS目录不存在，无需清理: {ts_path}")
                return

            _LOGGER.debug(f"开始清理TS文件: {ts_path}")

            # 删除TS文件
            ts_files_removed = 0
            for filename in os.listdir(ts_path):
                file_path = os.path.join(ts_path, filename)
                if os.path.isfile(file_path):
                    try:
                        os.remove(file_path)
                        ts_files_removed += 1
                        _LOGGER.debug(f"已删除文件: {filename}")
                    except Exception as e:
                        _LOGGER.warning(f"删除文件失败 {filename}: {e}")

            # 删除TS目录
            try:
                os.rmdir(ts_path)
                _LOGGER.debug(f"已删除TS目录: {ts_path}")
            except OSError as e:
                _LOGGER.warning(f"删除TS目录失败 {ts_path}: {e}")

            # 尝试删除父目录（如果为空）
            try:
                if os.path.exists(video_dir_path) and not os.listdir(video_dir_path):
                    os.rmdir(video_dir_path)
                    _LOGGER.debug(f"已删除空的视频目录: {video_dir_path}")
            except OSError as e:
                _LOGGER.debug(f"保留视频目录（非空或有其他文件）: {video_dir_path}")

            _LOGGER.info(f"TS文件清理完成，删除了 {ts_files_removed} 个文件")

        except Exception as e:
            _LOGGER.error(f"清理TS文件时出错: {e}")

    def _cleanup_event_folder(self, event_folder_path):
        """清理整个事件文件夹"""
        try:
            if not os.path.exists(event_folder_path):
                _LOGGER.debug(f"事件文件夹不存在，无需清理: {event_folder_path}")
                return

            _LOGGER.debug(f"开始清理事件文件夹: {event_folder_path}")

            # 删除文件夹内的所有内容
            items_removed = 0
            for item_name in os.listdir(event_folder_path):
                item_path = os.path.join(event_folder_path, item_name)
                try:
                    if os.path.isfile(item_path):
                        os.remove(item_path)
                        _LOGGER.debug(f"已删除文件: {item_name}")
                    elif os.path.isdir(item_path):
                        # 递归删除子目录
                        import shutil
                        shutil.rmtree(item_path)
                        _LOGGER.debug(f"已删除目录: {item_name}")
                    items_removed += 1
                except Exception as e:
                    _LOGGER.warning(f"删除项目失败 {item_name}: {e}")

            # 删除事件文件夹本身
            try:
                os.rmdir(event_folder_path)
                _LOGGER.debug(f"已删除事件文件夹: {event_folder_path}")
            except OSError as e:
                _LOGGER.warning(f"删除事件文件夹失败 {event_folder_path}: {e}")
                # 如果文件夹不为空，使用shutil强制删除
                try:
                    import shutil
                    shutil.rmtree(event_folder_path)
                    _LOGGER.debug(f"强制删除事件文件夹: {event_folder_path}")
                except Exception as e2:
                    _LOGGER.error(f"强制删除事件文件夹失败 {event_folder_path}: {e2}")

            _LOGGER.info(f"事件文件夹清理完成，删除了 {items_removed} 个项目")

        except Exception as e:
            _LOGGER.error(f"清理事件文件夹时出错: {e}")

    def get_video_m3u8_url(self, event: DoorbellEvent):
        mic = self.xiaomi_cloud
        fid = event.fileId
        pms = {
            "did": str(self.miot_did),
            "model": self.model,
            "fileId": fid,
            "isAlarm": True,
            "videoCodec": "H265",
        }
        api = mic.get_api_by_host(
            "business.smartcamera.api.io.mi.com", "common/app/m3u8"
        )
        pms = mic.rc4_params("GET", api, {"data": mic.json_encode(pms)})
        pms["yetAnotherServiceToken"] = mic.service_token
        url = f"{api}?{urlencode(pms)}"
        return url
