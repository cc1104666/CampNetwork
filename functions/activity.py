import os
from loguru import logger
import random
import asyncio
from .website_activity import handle_register
from .website_activity import process_wallet_quests, get_wallets_stats
from libs.eth_async.client import Client
from libs.eth_async.utils.utils import parse_proxy
from libs.eth_async.data.models import Networks
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config
from data.models import Settings
from fake_useragent import UserAgent

settings = Settings()
private_file = config.PRIVATE_FILE
if os.path.exists(private_file):
    with open(private_file, 'r') as private_file:
        private = [line.strip() for line in private_file if line.strip()]

proxy_file = config.PROXY_FILE
if os.path.exists(proxy_file):
    with open(proxy_file, 'r') as proxy_file:
        proxys = [line.strip() for line in proxy_file if line.strip()]


async def add_wallets_db():
    logger.info(f'Start import wallets')
    for i in range(len(private)):
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
        private_key = private[i]
        proxy = proxys[i]
        proxy = parse_proxy(proxy)
        client = Client(private_key=private_key,
                        network=Networks.Ethereum)
        async with Session() as session:
            db = DB(session=session)
            await db.add_wallet(private_key=private_key, public_key=client.account.address, proxy=proxy, user_agent=user_agent)

    logger.success('Success import wallets')
    return

async def start_register():
    async with Session() as session:
        db = DB(session=session)
        wallets = await db.get_all_wallets()
    tasks = [handle_register(user=user) for user in wallets]
    task_gathering = asyncio.gather(*tasks)
    await task_gathering

async def complete_all_wallets_quests(quest_list = None):
    """Выполняет задания для всех кошельков"""
    try:
        async with Session() as session:
            db = DB(session=session)
            wallets = await db.get_quests_wallets()
        
        if not wallets:
            logger.error("Нет кошельков в базе данных")
            return
        
        logger.info(f"Найдено {len(wallets)} кошельков, начинаю выполнение заданий")
        
        # Создаем задачи для всех кошельков
        tasks = []
        for wallet in wallets:
            # Если у кошелька нет токена сессии, пропускаем его
            if not wallet.camp_session_token:
                logger.warning(f"{wallet} пропущен - нет токена сессии")
                continue
                
            # Добавляем небольшую случайную задержку между запуском обработки кошельков
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
            task = asyncio.create_task(process_wallet_quests(wallet, quest_list))
            tasks.append(task)
        
        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков с действительными сессиями")
            return
            
        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Анализируем результаты
        success_count = sum(1 for result in results if result is True)
        error_count = sum(1 for result in results if isinstance(result, Exception))
        failed_count = len(results) - success_count - error_count
        
        logger.info(f"Обработка завершена: успешно {success_count}, с ошибками {failed_count}, исключений {error_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")

async def get_stats():
    async with Session() as session:
        db = DB(session=session)
        wallets = await db.get_quests_wallets()
    
    if not wallets:
        logger.error("Нет кошельков в базе данных")
        return

    await get_wallets_stats(wallets=wallets) 
    logger.info(f"Найдено {len(wallets)} кошельков, начинаю сбор статистики")
    
