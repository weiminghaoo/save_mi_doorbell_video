import sys

import src.xiaomi_cloud as xiaomi_cloud
from src.doorbell import MiDoorbell
import src.config as config
import schedule
import time
import json
import os
import logging

_LOGGER = logging.getLogger(__name__)

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s',
                    datefmt='%m-%d %H:%M:%S')

# 设置doorbell模块的日志级别
doorbell_logger = logging.getLogger('doorbell')
doorbell_logger.setLevel(logging.DEBUG)


class MiDoorbellManager:
    """小米门铃管理器"""

    def __init__(self, config_path='config.json'):
        """初始化管理器"""
        self.conf = config.from_file(config_path)
        self.cloud = None
        self.device = None
        self.device_type = None
        # 确保save_path目录存在
        self._ensure_save_path()
        # data.json保存到save_path目录中
        self.data_path = os.path.join(self.conf.save_path, 'data.json')
        # 缓存文件路径
        self.cache_path = os.path.join(self.conf.save_path, 'auth_cache.json')
        _LOGGER.info('小米门铃管理器初始化完成，数据文件保存在: %s', self.data_path)

    def _ensure_save_path(self):
        """确保保存路径目录存在"""
        try:
            if not os.path.exists(self.conf.save_path):
                os.makedirs(self.conf.save_path, exist_ok=True)
                _LOGGER.info('创建保存目录: %s', self.conf.save_path)
        except Exception as e:
            _LOGGER.error('创建保存目录失败: %s', e)
            raise

    def _save_auth_cache(self):
        """保存登录状态到缓存"""
        try:
            if not self.cloud:
                return False

            cache_data = {
                'user_id': self.cloud.user_id,
                'service_token': self.cloud.service_token,
                'ssecurity': self.cloud.ssecurity,
                'cuser_id': self.cloud.cuser_id,
                'pass_token': self.cloud.pass_token,
                'timestamp': int(time.time()),
                'username': self.conf.username
            }

            with open(self.cache_path, 'w') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            _LOGGER.info('登录状态已缓存到: %s', self.cache_path)
            return True
        except Exception as e:
            _LOGGER.warning('保存登录缓存失败: %s', e)
            return False

    def _load_auth_cache(self):
        """从缓存加载登录状态"""
        try:
            if not os.path.exists(self.cache_path):
                return None

            with open(self.cache_path, 'r') as f:
                cache_data = json.load(f)

            # 检查缓存是否过期（24小时）
            cache_time = cache_data.get('timestamp', 0)
            current_time = int(time.time())
            if current_time - cache_time > 24 * 3600:  # 24小时过期
                _LOGGER.info('登录缓存已过期，将重新登录')
                return None

            # 检查用户名是否匹配
            if cache_data.get('username') != self.conf.username:
                _LOGGER.info('用户名不匹配，将重新登录')
                return None

            _LOGGER.info('发现有效的登录缓存')
            return cache_data
        except Exception as e:
            _LOGGER.warning('加载登录缓存失败: %s', e)
            return None

    def _apply_auth_cache(self, cache_data):
        """应用缓存的登录状态"""
        try:
            if not self.cloud:
                # 创建云服务实例但不登录
                self.cloud = xiaomi_cloud.MiotCloud(username=self.conf.username, password=self.conf.password)

            # 应用缓存的认证信息
            self.cloud.user_id = cache_data.get('user_id')
            self.cloud.service_token = cache_data.get('service_token')
            self.cloud.ssecurity = cache_data.get('ssecurity')
            self.cloud.cuser_id = cache_data.get('cuser_id')
            self.cloud.pass_token = cache_data.get('pass_token')

            _LOGGER.info('登录缓存应用成功')
            return True
        except Exception as e:
            _LOGGER.warning('应用登录缓存失败: %s', e)
            return False

    def _validate_auth(self):
        """验证当前登录状态是否有效"""
        try:
            if not self.cloud or not self.cloud.service_token:
                return False

            # 尝试获取设备列表来验证登录状态
            device_list = self.cloud.get_device_list()
            return device_list is not None
        except Exception as e:
            _LOGGER.debug('登录状态验证失败: %s', e)
            return False

    def _clear_auth_cache(self):
        """清除登录缓存"""
        try:
            if os.path.exists(self.cache_path):
                os.remove(self.cache_path)
                _LOGGER.info('登录缓存已清除')
            return True
        except Exception as e:
            _LOGGER.warning('清除登录缓存失败: %s', e)
            return False

    def login(self, force_relogin=False):
        """登录米家账号并初始化云服务"""
        try:
            # 如果不强制重新登录，先尝试使用缓存
            if not force_relogin:
                _LOGGER.info('检查登录缓存...')
                cache_data = self._load_auth_cache()

                if cache_data:
                    # 尝试应用缓存
                    if self._apply_auth_cache(cache_data):
                        # 验证缓存的有效性
                        if self._validate_auth():
                            _LOGGER.info('使用缓存登录成功')
                            return True
                        else:
                            _LOGGER.info('缓存登录验证失败，将重新登录')
                            self._clear_auth_cache()
                    else:
                        _LOGGER.info('缓存应用失败，将重新登录')
                        self._clear_auth_cache()
                else:
                    _LOGGER.info('未找到有效缓存，将进行登录')

            # 执行实际的登录流程
            self.cloud = xiaomi_cloud.MiotCloud(username=self.conf.username, password=self.conf.password)

            if self.conf.use_qr_login:
                _LOGGER.info('使用二维码登录米家账号...')
                self.cloud.qr_login()
                _LOGGER.info('二维码登录米家账号成功')
            else:
                _LOGGER.info('使用账号密码登录米家账号...')
                self.cloud.login()
                _LOGGER.info('账号密码登录米家账号成功')

            # 保存登录状态到缓存
            self._save_auth_cache()

            return True
        except Exception as e:
            _LOGGER.error('登录失败: %s', e)
            # 登录失败时清除可能损坏的缓存
            self._clear_auth_cache()
            raise

    def setup_device(self):
        """设置和配置智能设备"""
        try:
            # 获取米家设备列表
            device_list = self.cloud.get_device_list()
            _LOGGER.info('共获取到%d个设备', len(device_list))

            # 匹配智能门铃或门锁设备
            _LOGGER.info('正在自动匹配智能设备...')
            device = None
            device_type = None
            for d in device_list:
                # 自动匹配设备类型
                if d['model'].startswith('madv.cateye.'):
                    device = d
                    device_type = '门铃'
                    _LOGGER.info('找到智能门铃设备: %s', d['name'])
                    break
                elif d['model'].startswith('xiaomi.lock.'):
                    device = d
                    device_type = '门锁'
                    _LOGGER.info('找到智能门锁设备: %s', d['name'])
                    break

            if not device:
                # 未找到支持设备
                _LOGGER.error('未找到支持的智能设备(门铃/门锁)，请确认以下设备是否包含支持设备：')
                for device in device_list:
                    device_model = device['model']
                    if device_model.startswith('madv.cateye.'):
                        device_type_hint = ' (智能门铃)'
                    elif device_model.startswith('xiaomi.lock.'):
                        device_type_hint = ' (智能门锁)'
                    else:
                        device_type_hint = ''
                    _LOGGER.error('%s(%s)%s', device['name'], device['model'], device_type_hint)
                _LOGGER.error('提示: 当前支持的设备类型:')
                _LOGGER.error('  - 智能门铃: madv.cateye.*')
                _LOGGER.error('  - 智能门锁: xiaomi.lock.*')
                sys.exit(1)

            if device_type == '门铃':
                self.device = MiDoorbell(self.cloud, device['name'], device['did'], device['model'])
                _LOGGER.info('匹配门铃设备成功，设备名称为:%s(%s)', self.device.name, self.device.model)
            elif device_type == '门锁':
                # TODO: 这里可以添加门锁设备的处理逻辑
                self.device = MiDoorbell(self.cloud, device['name'], device['did'], device['model'])
                _LOGGER.info('匹配门锁设备成功，设备名称为:%s(%s)', device['name'], device['model'])

            self.device_type = device_type
            return True
        except Exception as e:
            _LOGGER.error('设备设置失败: %s', e)
            raise

    def check_and_download(self):
        """检查并下载门铃视频"""
        try:
            # 读取已经处理过的视频，避免重复处理
            data = self._load_processed_data()

            # 获取门铃事件列表(过滤历史已处理)
            event_list = [event for event in self.device.get_event_list() if event.fileId not in data]
            _LOGGER.info('本次共获取到%d条门铃事件', len(event_list))

            # 处理并下载视频
            for event in event_list:
                data[event.fileId] = event._asdict()

                _LOGGER.info(event.event_desc() + ',视频下载中...')
                # 保存视频到指定文件
                _LOGGER.debug(f'配置信息: save_path="{self.conf.save_path}", merge={self.conf.merge}, ffmpeg="{self.conf.ffmpeg}", cleanup_ts_files={self.conf.cleanup_ts_files}')
                device_name = self.device.name
                path = self.device.download_video(event, self.conf.save_path, self.conf.merge, self.conf.ffmpeg, self.conf.cleanup_ts_files, device_name)
                _LOGGER.info('视频已保存到：%s', path)

            # 存储已经处理过的记录
            self._save_processed_data(data)
            _LOGGER.info('本次共处理%d条门铃事件, 历史总处理%d条门铃事件', len(event_list), len(data))
            return len(event_list)
        except Exception as e:
            _LOGGER.error('检查和下载视频时出错: %s', e)
            return 0

    def _load_processed_data(self):
        """加载已处理的数据"""
        data = {}
        if os.path.exists(self.data_path):
            with open(self.data_path, 'r') as f:
                data = json.load(f)
        return data

    def _save_processed_data(self, data):
        """保存已处理的数据，包含设备信息"""
        # 添加设备信息到数据中
        if hasattr(self, 'device') and self.device:
            device_info = {
                'name': self.device.name,
                'did': self.device.miot_did,
                'model': self.device.model,
                'type': self.device_type
            }

            # 如果数据中已有设备信息，检查是否一致
            if 'device_info' in data:
                if data['device_info'] != device_info:
                    _LOGGER.info('设备信息已更新，新设备: %s', device_info['name'])
            else:
                _LOGGER.info('添加设备信息: %s', device_info['name'])

            data['device_info'] = device_info

        with open(self.data_path, 'w') as fp:
            json.dump(data, fp, ensure_ascii=False, indent=True)

    def initialize(self):
        """初始化整个系统"""
        try:
            # 登录前置步骤
            _LOGGER.info('开始登录流程...')
            self.login()

            # 设备设置步骤
            _LOGGER.info('开始设备设置...')
            self.setup_device()

            # 检查并下载视频
            _LOGGER.info('开始检查和下载视频...')
            self.check_and_download()

            return True
        except Exception as e:
            _LOGGER.error('系统初始化失败: %s', e)
            raise

    def run_scheduler(self):
        """运行定时调度器"""
        _LOGGER.info('设置定时任务，每%d分钟执行一次', self.conf.schedule_minutes)
        schedule.every(self.conf.schedule_minutes).minutes.do(self.check_and_download)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            _LOGGER.info('程序被用户中断')
        except Exception as e:
            _LOGGER.error('定时任务运行出错: %s', e)

    def force_relogin(self):
        """强制重新登录，清除缓存"""
        try:
            _LOGGER.info('强制重新登录，清除缓存...')
            self._clear_auth_cache()
            return self.login(force_relogin=True)
        except Exception as e:
            _LOGGER.error('强制重新登录失败: %s', e)
            raise

    def get_cache_info(self):
        """获取缓存信息"""
        try:
            if not os.path.exists(self.cache_path):
                return {"status": "no_cache", "message": "无缓存文件"}

            with open(self.cache_path, 'r') as f:
                cache_data = json.load(f)

            cache_time = cache_data.get('timestamp', 0)
            current_time = int(time.time())
            age_hours = (current_time - cache_time) / 3600

            return {
                "status": "has_cache",
                "username": cache_data.get('username'),
                "cache_time": cache_time,
                "age_hours": round(age_hours, 1),
                "expired": age_hours > 24
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run(self):
        """运行完整流程"""
        try:
            self.initialize()
            self.run_scheduler()
        except Exception as e:
            _LOGGER.error('程序运行失败: %s', e)
            sys.exit(1)


if __name__ == '__main__':
    manager = MiDoorbellManager()
    manager.run()
