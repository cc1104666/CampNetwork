import os
from loguru import logger


from libs.eth_async.client import Client
import aiohttp
from libs.eth_async.data.models import Networks
from utils.db_api_async.models import User
from website.website import WebSite
from website.camp_quest import CampQuestManager

async def handle_register(user: User):
    try:
        client = Client(private_key=user.private_key,
                        network=Networks.Arbitrum,
                        proxy=user.proxy, check_proxy=True)
    except Exception as e:
        print(e)
        logger.error(f'{user} bad proxy')
        return
    logger.info(f'Start working with {user}')
    connector = aiohttp.TCPConnector(limit=10, force_close=False, keepalive_timeout=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        website = WebSite(user=user, client=client, session=session)
        await website.login()
    return

async def process_wallet_quests(user: User, quest_list = None):
    """Обрабатывает задания для одного кошелька"""
    try:
        # Проверяем, есть ли у пользователя токен сессии
        if not user.camp_session_token:
            logger.warning(f"{user} нет токена сессии, сначала выполните авторизацию")
            return False
        
        async with aiohttp.ClientSession() as session:
            # Создаем менеджер квестов
            quest_manager = CampQuestManager(user=user, session=session)
            
            # Проверяем сессию
            session_info = await quest_manager.get_session_info()
            if not session_info or 'user' not in session_info:
                logger.error(f"{user} сессия недействительна, требуется повторная авторизация")
                return False
            
            # Если указан список квестов, выполняем только их
            if quest_list:
                logger.info(f"{user} выполняю указанные задания: {', '.join(quest_list)}")
                results = await quest_manager.complete_specific_quests(quest_list)
            else:
                # Иначе выполняем все незавершенные задания
                logger.info(f"{user} выполняю все незавершенные задания")
                results = await quest_manager.complete_all_quests()
            
            # Получаем статистику
            stats = await quest_manager.get_stats()
            
            # Формируем сообщение с результатами
            completed_quests = [name for name, status in results.items() if status]
            failed_quests = [name for name, status in results.items() if not status]
            
            if completed_quests:
                logger.success(f"{user} успешно выполнены задания: {', '.join(completed_quests)}")
            if failed_quests:
                logger.warning(f"{user} не удалось выполнить задания: {', '.join(failed_quests)}")
                
            logger.info(f"{user} статистика: {stats['completed_count']}/{stats['total_count']} заданий, {stats['total_points']} баллов")
            
            return True
            
    except Exception as e:
        logger.error(f"{user} ошибка при обработке заданий: {str(e)}")
        return False


async def get_wallets_stats(wallets: list):
    """Получает статистику по всем кошелькам"""
    try:
        if not wallets:
            logger.error("Нет кошельков в базе данных")
            return
        
        logger.info(f"Получаю статистику для {len(wallets)} кошельков")
        
        # Создаем словарь для хранения статистики
        stats = {}
        
        # Для каждого кошелька получаем статистику
        for wallet in wallets:
            # Если у кошелька нет токена сессии, пропускаем
            if not wallet.camp_session_token:
                stats[wallet.public_key] = {"error": "Нет токена сессии"}
                continue
                
            async with aiohttp.ClientSession() as session:
                quest_manager = CampQuestManager(user=wallet, session=session)
                wallet_stats = await quest_manager.get_stats()
                stats[wallet.public_key] = wallet_stats
        
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
