import os
import random
from loguru import logger
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config
from data.models import Settings

def load_ref_codes():
    """Загружает реферальные коды из файла"""
    ref_codes_file = config.REF_CODES_FILE
    if os.path.exists(ref_codes_file) and os.path.getsize(ref_codes_file) > 0:
        with open(ref_codes_file, 'r') as file:
            return [line.strip() for line in file if line.strip()]
    return []

async def get_referral_code_for_registration(use_random_from_db: bool = True):
    """
    Получает реферальный код для регистрации
    
    Args:
        use_random_from_db: Использовать случайный код из БД
        
    Returns:
        Реферальный код или None
    """
    # Сначала пробуем загрузить коды из файла
    file_codes = load_ref_codes()
    
    # Если указано использовать случайный код из БД и файл пустой
    if use_random_from_db:
        try:
            # Получаем коды из БД
            async with Session() as session:
                db = DB(session=session)
                db_codes = await db.get_available_ref_codes()
                
                if db_codes:
                    return random.choice(db_codes)
                else:
                    return random.choice(file_codes)
        except Exception as e:
            logger.error(f"Ошибка при получении реферальных кодов из БД: {str(e)}")
    
    # Если есть коды в файле, используем их
    if file_codes:
        return random.choice(file_codes)
        
    return None

async def add_ref_code_to_file(ref_code: str) -> bool:
    """
    Добавляет реферальный код в файл
    
    Args:
        ref_code: Реферальный код
        
    Returns:
        Статус успеха
    """
    try:
        with open(config.REF_CODES_FILE, 'a') as f:
            f.write(f"{ref_code}\n")
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении кода в файл: {str(e)}")
        return False

async def update_ref_codes_file_from_db() -> bool:
    """
    Обновляет файл с реферальными кодами из базы данных
    
    Returns:
        Статус успеха
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
        logger.error(f"Ошибка при обновлении файла с кодами: {str(e)}")
        return False
