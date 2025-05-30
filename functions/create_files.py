import os
import csv

from libs.eth_async.utils.utils import update_dict
from libs.eth_async.utils.files import touch, write_json, read_json

from data import config


def create_files():
    touch(path=config.FILES_DIR)

    if not os.path.exists(config.REF_CODES_FILE):
        with open(config.REF_CODES_FILE, 'w') as f:
            pass

    if not os.path.exists(config.PRIVATE_FILE):
        with open(config.PRIVATE_FILE, 'w') as f:
            pass

    if not os.path.exists(config.PROXY_FILE):
        with open(config.PROXY_FILE, 'w') as f:
            pass
    if not os.path.exists(config.TWITTER_FILE):
        with open(config.TWITTER_FILE, 'w') as f:
            pass
            
    # 创建备用资源文件
    if not os.path.exists(config.RESERVE_PROXY_FILE):
        with open(config.RESERVE_PROXY_FILE, 'w') as f:
            pass
    if not os.path.exists(config.RESERVE_TWITTER_FILE):
        with open(config.RESERVE_TWITTER_FILE, 'w') as f:
            pass

    try:
        current_settings: dict | None = read_json(path=config.SETTINGS_FILE)
    except Exception:
        current_settings = {}

    settings = {
        # Twitter 设置
        "twitter": {
            "enabled": True,
            "delay_between_actions": {
                "min": 120,  # 秒
                "max": 180  # 秒
            },
            "delay_between_quests": {
                "min": 300,  # 秒
                "max": 600   # 秒
            }
        },
        # 常规设置
        "quests": {
            "delay_between_quests": {
                "min": 20,  # 秒
                "max": 40   # 秒
            }
        },
        "referrals": {
            "use_random_from_db": True,  # 使用数据库中的随机码
            "use_only_file_codes": False  # 仅使用文件中的码
        },
        # 账户启动设置
        "wallets": {
            "range": {
                "start": 0,  # 起始索引
                "end": 0     # 结束索引 (0 = 全部)
            },
            "startup_delay": {
                "min": 0,   # 秒
                "max": 7200   # 秒
            }
        },
        # 资源设置
        "resources": {
            "auto_replace": True,  # 自动替换不良资源
            "max_failures": 3      # 标记资源为不良前的最大错误次数
        }
    }
    write_json(path=config.SETTINGS_FILE, obj=update_dict(modifiable=current_settings, template=settings), indent=2)
create_files()
