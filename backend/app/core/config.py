import os
import yaml
from typing import Dict, Any
import logging

# 配置文件路径
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config.yml")

# 添加日志记录
logger = logging.getLogger(__name__)
logger.info(f"配置文件路径: {CONFIG_PATH}")

# 配置缓存
_config_cache: Dict[str, Any] = {}

def get_config() -> Dict[str, Any]:
    """
    获取配置信息，支持热加载
    """
    global _config_cache
    # 检查文件修改时间是否变化，实现热加载
    try:
        if not os.path.exists(CONFIG_PATH):
            logger.error(f"配置文件不存在: {CONFIG_PATH}")
            raise FileNotFoundError(f"配置文件不存在: {CONFIG_PATH}")
            
        mod_time = os.path.getmtime(CONFIG_PATH)
        if not _config_cache or _config_cache.get("_mod_time") != mod_time:
            logger.info(f"正在加载配置文件: {CONFIG_PATH}")
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                config["_mod_time"] = mod_time
                _config_cache = config
                logger.info("配置已重新加载")
    except Exception as e:
        logger.error(f"加载配置文件失败: {str(e)}")
        if not _config_cache:
            # 如果缓存为空且加载失败，使用默认配置
            _config_cache = {
                "system": {
                    "title": "智能充电桩调度计费系统",
                    "version": "1.0.0",
                    "debug": True,
                    "host": "0.0.0.0",
                    "port": 8000
                },
                "database": {
                    "host": "localhost",
                    "port": 3306,
                    "user": "root",
                    "password": "20031216cyh",
                    "database": "smart_charge"
                },
                "station": {
                    "FastChargingPileNum": 2,
                    "TrickleChargingPileNum": 3,
                    "WaitingAreaSize": 6,
                    "ChargingQueueLen": 2,
                    "FastPower": 30,
                    "SlowPower": 7,
                    "ServiceRate": 0.8
                }
            }
            logger.warning("使用默认配置，加载配置文件失败")
        else:
            logger.warning("配置热加载失败，使用缓存配置")
    
    return _config_cache

# 数据库连接URL
def get_db_url() -> str:
    """
    获取数据库连接URL
    """
    config = get_config()
    db_config = config.get("database", {})
    return (
        f"mysql+pymysql://{db_config.get('user', 'root')}:"
        f"{db_config.get('password', '20031216cyh')}@"
        f"{db_config.get('host', 'localhost')}:"
        f"{db_config.get('port', 3306)}/"
        f"{db_config.get('database', 'smart_charge')}"
    )

# 获取系统配置
def get_system_config() -> Dict[str, Any]:
    """
    获取系统配置
    """
    return get_config().get("system", {})

# 获取充电站配置
def get_station_config() -> Dict[str, Any]:
    """
    获取充电站配置
    """
    return get_config().get("station", {})

# 获取费率配置
def get_rate_config() -> Dict[str, Any]:
    """
    获取费率配置
    """
    return get_config().get("rate", {}) 