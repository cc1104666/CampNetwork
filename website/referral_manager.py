import os
import random
from loguru import logger
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config
from data.models import Settings

def load_ref_codes():
    """从文件加载推荐码"""
    ref_codes_file = config.REF_CODES_FILE
    if os.path.exists(ref_codes_file) and os.path.getsize(ref_codes_file) > 0:
        with open(ref_codes_file, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    return []

async def get_referral_code_for_registration(use_random_from_db: bool = True):
    """
    获取注册用的推荐码
    
    Args:
        use_random_from_db: 是否使用数据库中的随机码
        
    Returns:
        推荐码或 None
    """
    # 首先尝试从文件加载码
    file_codes = load_ref_codes()
    
    # 如果指定使用数据库中的随机码且文件为空
    if use_random_from_db:
        try:
            # 从数据库获取码
            async with Session() as session:
                db = DB(session=session)
                db_codes = await db.get_available_ref_codes()
                
                if db_codes:
                    return random.choice(db_codes)
                else:
                    return random.choice(file_codes)
        except Exception as e:
            logger.error(f"从数据库获取推荐码时出错: {str(e)}")
    
    # 如果文件中有码，使用它们
    if file_codes:
        return random.choice(file_codes)
        
    return None

async def add_ref_code_to_file(ref_code: str) -> bool:
    """
    将推荐码添加到文件
    
    Args:
        ref_code: 推荐码
        
    Returns:
        成功状态
    """
    try:
        with open(config.REF_CODES_FILE, 'a') as f:
            f.write(f"{ref_code}\n")
        return True
    except Exception as e:
        logger.error(f"添加码到文件时出错: {str(e)}")
        return False

async def update_ref_codes_file_from_db() -> bool:
    """
    从数据库更新推荐码文件
    
    Returns:
        成功状态
    """
    try:
        async with Session() as session:
            db = DB(session=session)
            db_codes = await db.get_available_ref_codes()
            
            if db_codes:
                with open(config.REF_CODES_FILE, 'w') as f:
                    for code in db_codes:
                        f.write(f"{code}\n")
                return True
            return False
    except Exception as e:
        logger.error(f"更新码文件时出错: {str(e)}")
        return False
