import os
from loguru import logger
import random
import asyncio
from website.camp_client import CampNetworkClient
from website.twitter import TwitterClient
from website.quest_client import QuestClient
from libs.eth_async.client import Client
from libs.eth_async.utils.utils import parse_proxy
from libs.eth_async.data.models import Networks
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config
from data.config import ACTUAL_FOLLOWS_TWITTER, ACTUAL_UA
from data.models import Settings

settings = Settings()

# Загружаем данные из файлов
private_file = config.PRIVATE_FILE
if os.path.exists(private_file):
    with open(private_file, 'r') as private_file:
        private = [line.strip() for line in private_file if line.strip()]
else:
    private = []

proxy_file = config.PROXY_FILE
if os.path.exists(proxy_file):
    with open(proxy_file, 'r') as proxy_file:
        proxys = [line.strip() for line in proxy_file if line.strip()]
else:
    proxys = []

twitter_file = config.TWITTER_FILE
if os.path.exists(twitter_file):
    with open(twitter_file, 'r') as twitter_file:
        twitter = [line.strip() for line in twitter_file if line.strip()]
else:
    twitter = []

async def add_wallets_db():
    """Импортирует кошельки в базу данных"""
    if not private:
        logger.error("Нет приватных ключей в файле private.txt")
        return

    logger.info(f'Импортирую {len(private)} кошельков в базу данных')
    for i in range(len(private)):
        user_agent = ACTUAL_UA
        private_key = private[i]
        proxy = proxys[i] if i < len(proxys) else None
        proxy = parse_proxy(proxy) if proxy else None
        twitter_token = twitter[i] if i < len(twitter) else None
        
        try:
            client = Client(private_key=private_key, network=Networks.Ethereum)
            public_key = client.account.address
            
            async with Session() as session:
                db = DB(session=session)
                success = await db.add_wallet(
                    private_key=private_key,
                    public_key=public_key,
                    proxy=proxy,
                    user_agent=user_agent,
                    twitter_token=twitter_token
                )
                
                if success:
                    logger.success(f"Кошелек {public_key} добавлен в базу данных")
                else:
                    logger.warning(f"Кошелек {public_key} уже существует в базе данных")
        except Exception as e:
            logger.error(f"Ошибка при добавлении кошелька: {str(e)}")

    logger.success('Импорт кошельков завершен')
    return

async def process_wallet(wallet):
    """
    Обрабатывает все задания для одного кошелька с интеграцией Twitter
    
    Args:
        wallet: Объект кошелька
        
    Returns:
        Статус успеха
    """
    try:
        logger.info(f'Начинаю работу с {wallet}')
        
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)
        
        # Авторизуемся на сайте
        auth_success = await camp_client.login()
        if not auth_success:
            logger.error(f"{wallet} не удалось авторизоваться на CampNetwork")
            return False
        
        # Проверяем, включен ли Twitter
        twitter_enabled = settings.twitter_enabled and wallet.twitter_token is not None
        
        # Получаем список незавершенных заданий
        async with Session() as session:
            db = DB(session=session)
            completed_quests_ids = wallet.completed_quests.split(',') if wallet.completed_quests else []
            all_quests_ids = list(QuestClient.QUEST_IDS.values())
            
            # Фильтруем только те задания, которые еще не выполнены
            incomplete_quests_ids = [quest_id for quest_id in all_quests_ids if quest_id not in completed_quests_ids]
            
            # Преобразуем ID заданий обратно в имена
            incomplete_quests = []
            for quest_id in incomplete_quests_ids:
                for quest_name, qid in QuestClient.QUEST_IDS.items():
                    if qid == quest_id:
                        incomplete_quests.append(quest_name)
                        break
        
        if not incomplete_quests:
            logger.success(f"{wallet} все задания уже выполнены")
            return True
        
        # Перемешиваем список заданий для рандомизации
        random.shuffle(incomplete_quests)
        
        # Получаем настройки задержек для обычных заданий
        regular_min_delay, regular_max_delay = settings.get_quest_delay()
        
        # Выполняем обычные задания
        logger.info(f"{wallet} выполняю регулярные задания ({len(incomplete_quests)})")
        
        regular_completed = 0
        for quest_name in incomplete_quests:
            try:
                logger.info(f"{wallet} выполняю задание {quest_name}")
                result = await camp_client.quest_client.complete_quest(quest_name)
                
                if result:
                    logger.success(f"{wallet} успешно выполнено задание {quest_name}")
                    regular_completed += 1
                else:
                    logger.warning(f"{wallet} не удалось выполнить задание {quest_name}")
                
                # Задержка между заданиями
                delay = random.uniform(regular_min_delay, regular_max_delay)
                logger.info(f"{wallet} задержка {int(delay)} сек. перед следующим заданием")
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"{wallet} ошибка при выполнении задания {quest_name}: {str(e)}")
                await asyncio.sleep(regular_min_delay)  # Минимальная задержка перед следующим заданием
                continue
        
        # Выполняем Twitter задания, если Twitter включен
        twitter_completed = False
        if twitter_enabled:
            logger.info(f"{wallet} выполняю Twitter задания")
            
            try:
                # Создаем Twitter клиент для выполнения заданий
                twitter_client = TwitterClient(
                    user=wallet,
                    auth_client=camp_client.auth_client,
                    twitter_auth_token=wallet.twitter_token
                )
                
                # Выполняем Twitter задания
                twitter_result = await twitter_client.complete_twitter_quests(
                    follow_accounts=ACTUAL_FOLLOWS_TWITTER
                )
                
                twitter_completed = twitter_result
            except Exception as e:
                logger.error(f"{wallet} ошибка при выполнении Twitter заданий: {str(e)}")
                twitter_completed = False
            
        # Получаем список выполненных квестов для проверки
        async with Session() as session:
            db = DB(session=session)
            final_completed_quests = await db.get_completed_quests(wallet.id)
            
        # Подсчитываем количество выполненных заданий
        completed_count = len(final_completed_quests) if final_completed_quests else 0
        total_count = len(QuestClient.QUEST_IDS)
        
        # Выводим итоговую статистику
        logger.success(f"{wallet} выполнение заданий завершено. Статус: {completed_count}/{total_count} заданий")
        logger.info(f"{wallet} успешно выполнено регулярных заданий: {regular_completed}")
        if twitter_enabled:
            logger.info(f"{wallet} Twitter задания выполнены: {'Да' if twitter_completed else 'Нет'}")
            
        return True
            
    except Exception as e:
        logger.error(f"{wallet} ошибка при обработке: {str(e)}")
        return False

async def process_wallet_with_specific_quests(wallet, quest_list):
    """
    Выполняет указанные задания для одного кошелька
    
    Args:
        wallet: Объект кошелька
        quest_list: Список заданий для выполнения
        
    Returns:
        Статус успеха
    """
    try:
        logger.info(f'Начинаю работу с {wallet} для заданий: {", ".join(quest_list)}')
        
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)
        
        # Авторизуемся на сайте
        auth_success = await camp_client.login()
        if not auth_success:
            logger.error(f"{wallet} не удалось авторизоваться на CampNetwork")
            return False
            
        # Проверяем, включен ли Twitter
        twitter_enabled = settings.twitter_enabled and wallet.twitter_token is not None
        
        # Фильтруем задания на Twitter и обычные
        twitter_quests = []
        regular_quests = []
        
        for quest in quest_list:
            if quest.startswith("Twitter") and twitter_enabled:
                twitter_quests.append(quest)
            else:
                regular_quests.append(quest)
        
        # Получаем настройки задержек
        regular_min_delay, regular_max_delay = settings.get_quest_delay()
        
        # Выполняем обычные задания в случайном порядке
        if regular_quests:
            # Перемешиваем задания для рандомизации
            random.shuffle(regular_quests)
            
            logger.info(f"{wallet} выполняю {len(regular_quests)} регулярных заданий")
            regular_completed = 0
            
            for quest_name in regular_quests:
                try:
                    logger.info(f"{wallet} выполняю задание {quest_name}")
                    result = await camp_client.quest_client.complete_quest(quest_name)
                    
                    if result:
                        logger.success(f"{wallet} успешно выполнено задание {quest_name}")
                        regular_completed += 1
                    else:
                        logger.warning(f"{wallet} не удалось выполнить задание {quest_name}")
                    
                    # Задержка между заданиями
                    delay = random.uniform(regular_min_delay, regular_max_delay)
                    logger.info(f"{wallet} задержка {int(delay)} сек. перед следующим заданием")
                    await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"{wallet} ошибка при выполнении задания {quest_name}: {str(e)}")
                    await asyncio.sleep(regular_min_delay)
                    continue
        
        # Выполняем Twitter задания, если они есть и Twitter включен
        twitter_completed = False
        if twitter_enabled and twitter_quests:
            logger.info(f"{wallet} выполняю {len(twitter_quests)} Twitter заданий")
            
            try:
                # Создаем Twitter клиент для выполнения заданий
                twitter_client = TwitterClient(
                    user=wallet,
                    auth_client=camp_client.auth_client,
                    twitter_auth_token=wallet.twitter_token
                )
                
                # Определяем параметры для разных типов Twitter заданий
                follow_needed = any(quest for quest in twitter_quests if "Follow" in quest)
                tweet_needed = any(quest for quest in twitter_quests if "Tweet" in quest)
                like_needed = any(quest for quest in twitter_quests if "Like" in quest)
                retweet_needed = any(quest for quest in twitter_quests if "Retweet" in quest)
                
                # Основные параметры для Twitter заданий
                follow_accounts = None
                tweet_text = None
                tweet_id_to_like = None
                tweet_id_to_retweet = None
                
                # Настраиваем параметры в зависимости от типа заданий
                if follow_needed:
                    follow_accounts = ACTUAL_FOLLOWS_TWITTER
                
                if tweet_needed:
                    tweet_text = "Excited to be exploring @CampNetwork! Amazing project with great potential. #CampNetwork #Web3 #Crypto " + str(random.randint(1000, 9999))
                
                if like_needed:
                    tweet_id_to_like = 1234567890123456789  # Замените на реальный ID
                
                if retweet_needed:
                    tweet_id_to_retweet = 234567890123456789  # Замените на реальный ID
                
                # Выполняем задания Twitter
                twitter_result = await twitter_client.complete_twitter_quests(
                    follow_accounts=follow_accounts,
                    tweet_text=tweet_text,
                    tweet_id_to_like=tweet_id_to_like,
                    tweet_id_to_retweet=tweet_id_to_retweet
                )
                
                twitter_completed = twitter_result
            except Exception as e:
                logger.error(f"{wallet} ошибка при выполнении Twitter заданий: {str(e)}")
                twitter_completed = False
        
        # Получаем список выполненных квестов для проверки
        async with Session() as session:
            db = DB(session=session)
            final_completed_quests = await db.get_completed_quests(wallet.id)
            
        # Подсчитываем количество выполненных заданий
        completed_count = len(final_completed_quests) if final_completed_quests else 0
        total_count = len(QuestClient.QUEST_IDS)
        
        logger.success(f"{wallet} выполнение заданий завершено. Статус: {completed_count}/{total_count} заданий")
        
        return True
            
    except Exception as e:
        logger.error(f"{wallet} ошибка при обработке: {str(e)}")
        return False

async def complete_all_wallets_quests():
    """Выполняет задания для всех кошельков"""
    try:
        # Получаем список кошельков из базы данных
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()
        
        if not all_wallets:
            logger.error("Нет кошельков в базе данных. Сначала импортируйте кошельки.")
            return
        
        # Определяем диапазон кошельков для обработки из настроек
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]
        
        # Отображаем информацию о количестве кошельков для обработки
        logger.info(f"Найдено {len(all_wallets)} кошельков")
        logger.info(f"Будет обработано {len(wallets)} кошельков (с {wallet_start+1} по {wallet_start+len(wallets)})")
        
        # Перемешиваем кошельки для рандомизации порядка
        random.shuffle(wallets)
        
        # Получаем настройки задержки между запуском аккаунтов
        startup_min, startup_max = settings.get_wallet_startup_delay()
        
        # Создаем задачи для всех кошельков
        tasks = []
        for i, wallet in enumerate(wallets):
            # Добавляем случайную задержку между запуском обработки кошельков
            delay = random.uniform(startup_min, startup_max)
            logger.info(f"Запуск кошелька {wallet} ({i+1}/{len(wallets)}) через {int(delay)} сек.")
            await asyncio.sleep(delay)
            
            # Создаем задачу для обработки кошелька
            task = asyncio.create_task(process_wallet(wallet))
            tasks.append(task)
        
        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для обработки")
            return
            
        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Анализируем результаты
        success_count = sum(1 for result in results if result is True)
        error_count = sum(1 for result in results if isinstance(result, Exception) or result is False)
        
        logger.info(f"Обработка завершена: успешно {success_count}, с ошибками {error_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")

async def complete_specific_quests():
    """Выполняет указанные задания для всех кошельков с учетом настроек"""
    try:
        # Получаем список кошельков из базы данных
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()
        
        if not all_wallets:
            logger.error("Нет кошельков в базе данных. Сначала импортируйте кошельки.")
            return
        
        # Определяем диапазон кошельков для обработки из настроек
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]
        
        # Перемешиваем кошельки для рандомизации
        random.shuffle(wallets)
        
        logger.info(f"Найдено {len(all_wallets)} кошельков")
        logger.info(f"Будет обработано {len(wallets)} кошельков (с {wallet_start+1} по {wallet_start+len(wallets)})")
        
        # Получаем список доступных заданий
        quests = list(QuestClient.QUEST_IDS.keys())
        
        # Если Twitter включен, добавляем Twitter задания
        if settings.twitter_enabled:
            quests.extend(["TwitterFollow"])
        
        print("\n=== Доступные задания ===")
        for i, quest_name in enumerate(quests, 1):
            print(f"{i}. {quest_name}")
        
        print("\nВведите номера заданий через запятую (или 'all' для всех):")
        quest_input = input("> ").strip()
        
        if quest_input.lower() == 'all':
            selected_quests = quests
        else:
            try:
                # Парсим введенные номера
                quest_numbers = [int(num.strip()) for num in quest_input.split(",") if num.strip()]
                selected_quests = [quests[num-1] for num in quest_numbers if 1 <= num <= len(quests)]
                
                if not selected_quests:
                    logger.error("Не выбрано ни одного задания")
                    return
            except (ValueError, IndexError):
                logger.error(f"Некорректный ввод. Номер задания должен быть от 1 до {len(quests)}")
                return
        
        logger.info(f"Выбраны задания: {', '.join(selected_quests)}")
        
        # Получаем настройки задержки между запуском аккаунтов
        startup_min, startup_max = settings.get_wallet_startup_delay()
        
        # Создаем задачи для всех кошельков
        tasks = []
        for i, wallet in enumerate(wallets):
            # Добавляем случайную задержку между запуском обработки кошельков
            delay = random.uniform(startup_min, startup_max)
            logger.info(f"Запуск кошелька {wallet} ({i+1}/{len(wallets)}) через {int(delay)} сек.")
            await asyncio.sleep(delay)
            
            # Создаем задачу для обработки кошелька
            task = asyncio.create_task(process_wallet_with_specific_quests(wallet, selected_quests))
            tasks.append(task)
        
        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для обработки")
            return
            
        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Анализируем результаты
        success_count = sum(1 for result in results if result is True)
        error_count = sum(1 for result in results if isinstance(result, Exception) or result is False)
        
        logger.info(f"Обработка завершена: успешно {success_count}, с ошибками {error_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")

async def get_wallets_stats():
    """Получает статистику по всем кошелькам из базы данных, включая Twitter интеграцию"""
    try:
        # Получаем все кошельки из базы данных
        async with Session() as session:
            db = DB(session=session)
            wallets = await db.get_all_wallets()
        
        if not wallets:
            logger.error("Нет кошельков в базе данных")
            return
        
        logger.info(f"Получаю статистику для {len(wallets)} кошельков")
        
        # Создаем словарь для обратного поиска названий по ID
        quest_names_by_id = {quest_id: quest_name for quest_name, quest_id in QuestClient.QUEST_IDS.items()}
        
        # Создаем словарь для хранения статистики
        stats = {}
        
        # Для каждого кошелька получаем статистику из БД
        for wallet in wallets:
            try:
                # Получаем список выполненных квестов
                completed_quests_ids = wallet.completed_quests.split(',') if wallet.completed_quests and wallet.completed_quests != '' else []
                completed_count = len(completed_quests_ids) if completed_quests_ids else 0
                
                # Получаем названия выполненных заданий по их ID
                completed_quest_names = []
                for quest_id in completed_quests_ids:
                    if quest_id in quest_names_by_id:
                        completed_quest_names.append(quest_names_by_id[quest_id])
                    else:
                        completed_quest_names.append(f"Unknown ({quest_id})")
                
                # Добавляем информацию о Twitter
                twitter_status = "Подключен" if wallet.twitter_token else "Не подключен"
                
                stats[wallet.public_key] = {
                    "completed_count": completed_count,
                    "total_count": len(QuestClient.QUEST_IDS),
                    "completed_quests": completed_quest_names,
                    "twitter_status": twitter_status
                }
                
            except Exception as e:
                stats[wallet.public_key] = {"error": str(e)}
        
        # Выводим статистику
        print("\n=== Статистика кошельков ===")
        
        # Сортируем кошельки по количеству выполненных заданий (по убыванию)
        sorted_wallets = sorted(
            stats.keys(), 
            key=lambda k: stats[k].get("completed_count", 0) if "error" not in stats[k] else -1, 
            reverse=True
        )
        
        for wallet_key in sorted_wallets:
            wallet_stats = stats[wallet_key]
            
            if "error" in wallet_stats:
                logger.warning(f"{wallet_key}: {wallet_stats['error']}")
            else:
                percent = int((wallet_stats['completed_count'] / wallet_stats['total_count']) * 100)
                status_color = "green" if percent == 100 else "yellow" if percent > 50 else "red"
                
                # Сокращаем адрес кошелька для компактности
                short_key = f"{wallet_key[:6]}...{wallet_key[-4:]}"
                
                logger.info(f"{short_key}: {wallet_stats['completed_count']}/{wallet_stats['total_count']} заданий ({percent}%), Twitter: {wallet_stats['twitter_status']}")
                
                # Если есть выполненные задания, выводим их списком
                if wallet_stats['completed_count'] > 0 and wallet_stats['completed_count'] < wallet_stats['total_count']:
                    completed_list = ", ".join(wallet_stats['completed_quests'])
                    logger.info(f"  Выполненные задания: {completed_list}")
                
        # Выводим общую статистику
        total_wallets = len(stats)
        completed_wallets = sum(1 for wallet in stats.values() if "error" not in wallet and wallet["completed_count"] == wallet["total_count"])
        average_completion = sum(wallet["completed_count"] for wallet in stats.values() if "error" not in wallet) / total_wallets if total_wallets > 0 else 0
        
        print("\n=== Общая статистика ===")
        print(f"Всего кошельков: {total_wallets}")
        print(f"Завершено полностью: {completed_wallets} ({int((completed_wallets/total_wallets)*100)}%)")
        print(f"Среднее количество выполненных заданий: {average_completion:.1f} из {len(QuestClient.QUEST_IDS)}")
        
        return stats
            
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return {}
