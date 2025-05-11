import os
from loguru import logger
import random
import asyncio
from website.camp_client import CampNetworkClient
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
        proxy = proxys[i] if i < len(proxys) else None
        proxy = parse_proxy(proxy) if proxy else None
        client = Client(private_key=private_key,
                        network=Networks.Ethereum)
        async with Session() as session:
            db = DB(session=session)
            await db.add_wallet(private_key=private_key, public_key=client.account.address, proxy=proxy, user_agent=user_agent)

    logger.success('Success import wallets')
    return

async def complete_all_wallets_quests(quest_list=None):
    """Выполняет задания для всех кошельков"""
    try:
        async with Session() as session:
            db = DB(session=session)
            wallets = await db.get_all_wallets()
        
        if not wallets:
            logger.error("Нет кошельков в базе данных")
            return
        
        logger.info(f"Найдено {len(wallets)} кошельков, начинаю выполнение заданий")
        
        # Создаем задачи для всех кошельков
        tasks = []
        for wallet in wallets:
            # Добавляем небольшую случайную задержку между запуском обработки кошельков
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
            # Создаем задачу для обработки кошелька
            if quest_list:
                task = asyncio.create_task(process_wallet_with_specific_quests(wallet, quest_list))
            else:
                task = asyncio.create_task(process_wallet_with_all_quests(wallet))
                
            tasks.append(task)
        
        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для обработки")
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

async def process_wallet_with_all_quests(wallet):
    """Обрабатывает все задания для одного кошелька"""
    try:
        logger.info(f'Начинаю работу с {wallet}')
        
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)
        
        # Выполняем все задания
        results = await camp_client.complete_all_quests()
        
        # Анализируем результаты
        if not results:
            logger.warning(f"{wallet} не выполнено ни одного задания")
            return False
            
        completed = sum(1 for result in results.values() if result)
        if completed > 0:
            logger.success(f"{wallet} успешно выполнено {completed} из {len(results)} заданий")
            return True
        else:
            logger.warning(f"{wallet} не удалось выполнить ни одного задания")
            return False
            
    except Exception as e:
        logger.error(f"{wallet} ошибка при обработке: {str(e)}")
        return False

async def process_wallet_with_specific_quests(wallet, quest_list):
    """Обрабатывает указанные задания для одного кошелька"""
    try:
        logger.info(f'Начинаю работу с {wallet} для заданий: {", ".join(quest_list)}')
        
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)
        
        # Выполняем указанные задания
        results = await camp_client.complete_specific_quests(quest_list)
        
        # Анализируем результаты
        if not results:
            logger.warning(f"{wallet} не выполнено ни одного задания")
            return False
            
        completed = sum(1 for result in results.values() if result)
        if completed > 0:
            logger.success(f"{wallet} успешно выполнено {completed} из {len(results)} заданий")
            return True
        else:
            logger.warning(f"{wallet} не удалось выполнить ни одного задания")
            return False
            
    except Exception as e:
        logger.error(f"{wallet} ошибка при обработке: {str(e)}")
        return False

async def get_wallets_stats():
    """Получает статистику по всем кошелькам"""
    try:
        async with Session() as session:
            db = DB(session=session)
            wallets = await db.get_all_wallets()
        
        if not wallets:
            logger.error("Нет кошельков в базе данных")
            return
        
        logger.info(f"Получаю статистику для {len(wallets)} кошельков")
        
        # Создаем словарь для хранения статистики
        stats = {}
        
        # Для каждого кошелька получаем статистику
        for wallet in wallets:
            try:
                # Создаем клиент CampNetwork
                camp_client = CampNetworkClient(user=wallet)
                
                # Авторизуемся и получаем статистику
                stats[wallet.public_key] = await camp_client.get_stats()
                
            except Exception as e:
                stats[wallet.public_key] = {"error": str(e)}
        
        # Выводим статистику
        logger.info("Статистика кошельков:")
        for wallet_key, wallet_stats in stats.items():
            if "error" in wallet_stats:
                logger.warning(f"{wallet_key}: {wallet_stats['error']}")
            else:
                logger.info(f"{wallet_key}: {wallet_stats['completed_count']}/{wallet_stats['total_count']} заданий, {wallet_stats['total_points']} баллов")
                
        return stats
            
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return {}
