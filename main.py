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

    def __init__(self, config_path='config/config.json'):
        """初始化管理器"""
        self.conf = config.from_file(config_path)
        self.cloud = None
        self.devices = {}  # 支持多设备 {device_did: device_instance}
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
        """设置和配置智能设备，支持多设备"""
        try:
            # 获取米家设备列表
            device_list = self.cloud.get_device_list()
            _LOGGER.info('共获取到%d个设备', len(device_list))

            # 匹配所有支持的智能设备
            _LOGGER.info('正在自动匹配智能设备...')
            supported_devices = []

            for d in device_list:
                device_type = None
                # 自动匹配设备类型
                if d['model'].startswith('madv.cateye.'):
                    device_type = '门铃'
                elif d['model'].startswith('xiaomi.lock.'):
                    device_type = '门锁'

                if device_type:
                    supported_devices.append((d, device_type))
                    _LOGGER.info('找到支持的设备: %s (%s)', d['name'], device_type)

            if not supported_devices:
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

            # 初始化所有找到的设备
            for device, device_type in supported_devices:
                device_instance = MiDoorbell(self.cloud, device['name'], device['did'], device['model'])
                self.devices[device['did']] = {
                    'instance': device_instance,
                    'type': device_type,
                    'info': device
                }
                _LOGGER.info('设备初始化成功: %s (%s)', device['name'], device_type)

            _LOGGER.info('总共初始化了 %d 个设备', len(self.devices))
            return True
        except Exception as e:
            _LOGGER.error('设备设置失败: %s', e)
            raise

    def check_and_download(self):
        """检查并下载所有设备的视频"""
        try:
            # 读取已经处理过的视频，避免重复处理
            data = self._load_processed_data()

            total_success = 0
            total_events = 0
            total_devices = len(self.devices)
            current_device_idx = 0

            # 遍历所有设备
            for device_did, device_info in self.devices.items():
                current_device_idx += 1
                device_instance = device_info['instance']
                device_type = device_info['type']
                device_name = device_instance.name

                _LOGGER.info('=== 开始处理设备 %d/%d: %s (%s) ===',
                            current_device_idx, total_devices, device_name, device_type)

                # 获取当前设备的数据
                device_key = str(device_did)
                device_data = data.get(device_key, {})

                # 获取门铃事件列表(过滤历史已处理)
                event_list = [event for event in device_instance.get_event_list() if event.fileId not in device_data]
                _LOGGER.info('设备 %s 本次共获取到%d条门铃事件', device_name, len(event_list))
                total_events += len(event_list)

                # 处理并下载视频
                success_count = 0
                total_device_events = len(event_list)

                for event_idx, event in enumerate(event_list, 1):
                    try:
                        device_data[event.fileId] = event._asdict()

                        _LOGGER.info('[%s] [%d/%d] %s,视频下载中...',
                                    device_name, event_idx, total_device_events, event.event_desc())
                        # 获取ffmpeg路径
                        ffmpeg_path = self.conf.get_ffmpeg_path()
                        _LOGGER.debug(f'使用FFmpeg路径: {ffmpeg_path}')

                        # 保存视频到指定文件
                        _LOGGER.debug(f'配置信息: save_path="{self.conf.save_path}", merge={self.conf.merge}, ffmpeg="{ffmpeg_path}", cleanup_ts_files={self.conf.cleanup_ts_files}')
                        path = device_instance.download_video(event, self.conf.save_path, self.conf.merge, ffmpeg_path, self.conf.cleanup_ts_files, device_name)
                        _LOGGER.info('[%s] [%d/%d] ✅ 视频已保存到：%s',
                                    device_name, event_idx, total_device_events, path)

                        # 更新数据结构并立即保存
                        data[device_key] = device_data
                        self._save_processed_data(data)
                        success_count += 1
                        total_success += 1
                        _LOGGER.debug('[%s] 已保存处理记录，当前成功: %d/%d', device_name, success_count, len(event_list))

                    except Exception as e:
                        _LOGGER.error('[%s] 处理事件 %s 时出错: %s', device_name, event.fileId, e)
                        # 从数据中移除失败的事件，避免重复处理
                        if event.fileId in device_data:
                            del device_data[event.fileId]
                        # 继续处理下一个事件，不中断整个流程
                        continue

                _LOGGER.info('=== 设备 %s 处理完成: %d/%d 条事件（成功/总数），历史总处理 %d 条事件 ===',
                            device_name, success_count, len(event_list), len(device_data))

            # 显示总体进度汇总
            _LOGGER.info('')
            _LOGGER.info('🎉 所有设备处理完成！')
            _LOGGER.info('📊 总体统计:')
            _LOGGER.info('   • 设备数量: %d 个', len(self.devices))
            _LOGGER.info('   • 总事件数: %d 条', total_events)
            _LOGGER.info('   • 成功下载: %d 条', total_success)
            _LOGGER.info('   • 成功率: %.1f%%', (total_success / total_events * 100) if total_events > 0 else 0)
            _LOGGER.info('')
            return total_success
        except Exception as e:
            _LOGGER.error('检查和下载视频时出错: %s', e)
            return 0

    def _load_processed_data(self):
        """加载已处理的数据"""
        data = {}
        if os.path.exists(self.data_path):
            with open(self.data_path, 'r') as f:
                data = json.load(f)

        # 检查是否需要从旧格式迁移
        if data and not any(isinstance(v, dict) and 'eventTime' in v for v in data.values() if isinstance(v, dict)):
            # 这是新格式（按设备组织），无需迁移
            pass
        elif data and hasattr(self, 'devices') and self.devices:
            # 旧格式迁移：为每个设备创建独立的数据结构
            old_events = data.copy()
            data = {}
            for device_did in self.devices.keys():
                data[str(device_did)] = old_events.copy()
            _LOGGER.info('已迁移旧数据格式到多设备结构，共 %d 个设备', len(self.devices))

        return data

    def _save_processed_data(self, data):
        """保存已处理的数据，按设备组织"""
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
