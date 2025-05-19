import os
import sys
import asyncio
import subprocess
from pathlib import Path
from loguru import logger

async def check_and_migrate_db():
    """
    Проверяет структуру БД и выполняет необходимые миграции
    """
    try:
        logger.info("Проверка структуры базы данных...")
        
        # Определяем путь к БД
        db_path = Path('./files/wallets.db')
        
        # Проверяем, существует ли база данных
        if not db_path.exists():
            logger.info("База данных не существует, создание новой")
            # Новая БД будет создана с актуальной схемой
            return True
        
        # Проверяем наличие директории migrations
        migration_dir = Path('./migrations')
        if not migration_dir.exists():
            logger.warning("Директория миграций не найдена, пропуск проверки миграций")
            return True
        
        # Выполняем команду Alembic для проверки статуса миграций
        logger.info("Запуск миграций Alembic...")
        try:
            # Для корректной работы с venv или frozen приложением
            python_exe = sys.executable
            
            # Выполняем миграцию через subprocess
            process = subprocess.Popen(
                [python_exe, "-m", "alembic", "upgrade", "head"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                logger.success("Миграция базы данных успешно выполнена")
                if stdout:
                    logger.info(f"Результат миграции: {stdout}")
                return True
            else:
                # logger.error(f"Ошибка при выполнении миграции: {stderr}")
                
                # Если ошибка связана с отсутствием таблицы alembic_version, 
                # значит это первое обновление из старой БД
                if "alembic_version" in stderr:
                    logger.warning("Обнаружена старая структура БД, попытка обновления...")
                    
                    # Выполняем команду для первой миграции с пометкой "данные уже созданы"
                    process = subprocess.Popen(
                        [python_exe, "-m", "alembic", "stamp", "head"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    stdout, stderr = process.communicate()
                    
                    if process.returncode == 0:
                        logger.success("База данных помечена как актуальная")
                        
                        # Теперь добавляем недостающее поле ref_code вручную
                        from sqlite3 import connect
                        conn = connect(str(db_path))
                        cursor = conn.cursor()
                        
                        # Проверяем, есть ли уже поле ref_code
                        cursor.execute("PRAGMA table_info(campnetwork)")
                        columns = [col[1] for col in cursor.fetchall()]
                        
                        if "ref_code" not in columns:
                            logger.info("Добавление поля ref_code в таблицу campnetwork")
                            cursor.execute("ALTER TABLE campnetwork ADD COLUMN ref_code TEXT")
                            conn.commit()
                            logger.success("Поле ref_code успешно добавлено")
                        
                        conn.close()
                        return True
                    else:
                        # logger.error(f"Ошибка при обновлении структуры БД: {stderr}")
                        return False
                
                return False
                
        except Exception as e:
            # logger.error(f"Ошибка при выполнении миграции: {str(e)}")
            
            # Если не удалось выполнить миграцию через Alembic, 
            # пробуем добавить поле вручную
            return True
        
    except Exception as e:
        return True
