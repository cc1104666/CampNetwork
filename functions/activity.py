import os
from loguru import logger
import random
import asyncio
from website.camp_client import CampNetworkClient
from website.twitter import TwitterQuestManager
from website.quest_client import QuestClient
from libs.eth_async.client import Client
from libs.eth_async.utils.utils import parse_proxy
from libs.eth_async.data.models import Networks
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config
from data.models import Settings

settings = Settings()
private_file = config.PRIVATE_FILE
if os.path.exists(private_file):
    with open(private_file, 'r') as private_file:
        private = [line.strip() for line in private_file if line.strip()]

proxy_file = config.PROXY_FILE
if os.path.exists(proxy_file):
    with open(proxy_file, 'r') as proxy_file:
        proxys = [line.strip() for line in proxy_file if line.strip()]

twitter_file = config.TWITTER_FILE
if os.path.exists(twitter_file):
    with open(twitter_file, 'r') as twitter_file:
        twitter = [line.strip() for line in twitter_file if line.strip()]

async def add_wallets_db():
    logger.info(f'Start import wallets')
    for i in range(len(private)):
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        private_key = private[i]
        proxy = proxys[i] if i < len(proxys) else None
        proxy = parse_proxy(proxy) if proxy else None
        twitter_token = twitter[i] if i < len (twitter) else None
        client = Client(private_key=private_key,
                        network=Networks.Ethereum)
        async with Session() as session:
            db = DB(session=session)
            await db.add_wallet(private_key=private_key, public_key=client.account.address, proxy=proxy, user_agent=user_agent, twitter_token=twitter_token)

    logger.success('Success import wallets')
    return

async def process_wallet_with_all_quests(wallet):
    """Обрабатывает все задания для одного кошелька с расширенной обработкой ошибок"""
    try:
        logger.info(f'Начинаю работу с {wallet}')
        
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)
        
        # Выполняем все задания
        results = await camp_client.complete_all_quests()
        
        # Проверяем, не был ли аккаунт ограничен по запросам
        if isinstance(results, dict) and results.get("status") == "RATE_LIMITED":
            logger.warning(f"{wallet} ограничен по запросам, пропускаем")
            return False
        
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
        logger.info(f"Обработка завершена: успешно {success_count}, с ошибками {error_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")

async def process_wallet(wallet):
    """Обрабатывает все задания для одного кошелька с интеграцией Twitter"""
    try:
        logger.info(f'Начинаю работу с {wallet}')
        
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)
        
        # Получаем список всех доступных квестов
        quests = list(QuestClient.QUEST_IDS.keys())
        
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
        
        logger.info(f"{wallet} найдено {len(incomplete_quests)} незавершенных заданий")
        
        # Если нет незавершенных заданий, выходим
        if not incomplete_quests:
            logger.success(f"{wallet} все задания уже выполнены")
            return True
        
        # Перемешиваем список заданий для рандомизации
        random.shuffle(incomplete_quests)
        
        # Определяем, какие задания относятся к Twitter
        twitter_quests = []
        regular_quests = []
        
        for quest in incomplete_quests:
            if quest.startswith("Twitter") and twitter_enabled:
                twitter_quests.append(quest)
            else:
                regular_quests.append(quest)
        
        # Объединяем списки заданий и перемешиваем их снова для случайного порядка выполнения
        # Если Twitter включен, комбинируем задания, иначе выполняем только обычные
        if twitter_enabled:
            # Смешиваем задания
            mixed_quests = []
            twitter_index = 0
            regular_index = 0
            
            # Решаем, начинать ли с Twitter задания или с обычного, случайным образом
            start_with_twitter = random.choice([True, False])
            
            while twitter_index < len(twitter_quests) or regular_index < len(regular_quests):
                # Если начинаем с Twitter, сначала добавляем Twitter задание, затем обычное
                if start_with_twitter:
                    if twitter_index < len(twitter_quests):
                        mixed_quests.append(("twitter", twitter_quests[twitter_index]))
                        twitter_index += 1
                    if regular_index < len(regular_quests):
                        mixed_quests.append(("regular", regular_quests[regular_index]))
                        regular_index += 1
                # Иначе сначала добавляем обычное задание, затем Twitter
                else:
                    if regular_index < len(regular_quests):
                        mixed_quests.append(("regular", regular_quests[regular_index]))
                        regular_index += 1
                    if twitter_index < len(twitter_quests):
                        mixed_quests.append(("twitter", twitter_quests[twitter_index]))
                        twitter_index += 1
        else:
            # Если Twitter отключен, используем только обычные задания
            mixed_quests = [("regular", quest) for quest in regular_quests]
        
        # Получаем настройки задержек
        regular_min_delay, regular_max_delay = settings.get_quest_delay()
        twitter_min_delay, twitter_max_delay = settings.get_twitter_quest_delay()
        
        # Выполняем задания в смешанном порядке
        for quest_type, quest_name in mixed_quests:
            try:
                result = None
                if quest_type == "regular":
                    # Выполняем обычное задание
                    logger.info(f"{wallet} выполняю задание {quest_name}")
                    result = await camp_client.quest_client.complete_quest(quest_name)
                    
                    if result:
                        logger.success(f"{wallet} успешно выполнено задание {quest_name}")
                    else:
                        logger.warning(f"{wallet} не удалось выполнить задание {quest_name}")
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(regular_min_delay, regular_max_delay))
                else:
                    # Выполняем Twitter задание
                    logger.info(f"{wallet} выполняю Twitter задание {quest_name}")
                    
                    # Создаем Twitter клиент и выполняем задание
                    twitter_manager = TwitterQuestManager(
                        user=wallet,
                        auth_client=camp_client.auth_client,
                        twitter_auth_token=wallet.twitter_token
                    )
                    
                    if "Follow" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=["CampNetwork", "campnetworkxyz"],
                            custom_tweet_text=None,
                            custom_tweet_to_like=None,
                            custom_tweet_to_retweet=None
                        )
                    elif "Tweet" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=None,
                            custom_tweet_text="Excited to be exploring @CampNetwork! Amazing project with great potential. #CampNetwork #Web3 #Crypto " + str(random.randint(1000, 9999)),
                            custom_tweet_to_like=None,
                            custom_tweet_to_retweet=None
                        )
                    elif "Like" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=None,
                            custom_tweet_text=None,
                            custom_tweet_to_like=1234567890123456789,  # Замените на реальный ID
                            custom_tweet_to_retweet=None
                        )
                    elif "Retweet" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=None,
                            custom_tweet_text=None,
                            custom_tweet_to_like=None,
                            custom_tweet_to_retweet=234567890123456789  # Замените на реальный ID
                        )
                    
                    # Проверяем результат выполнения
                    quest_result = result
                    if quest_result:
                        logger.success(f"{wallet} успешно выполнено Twitter задание {quest_name}")
                    else:
                        logger.warning(f"{wallet} не удалось выполнить Twitter задание {quest_name}")
                    
                    # Задержка между Twitter заданиями
                    await asyncio.sleep(random.uniform(twitter_min_delay, twitter_max_delay))
            
            except Exception as e:
                logger.error(f"{wallet} ошибка при выполнении задания {quest_name}: {str(e)}")
                # Продолжаем с следующим заданием
                await asyncio.sleep(random.uniform(regular_max_delay, twitter_min_delay))
                continue
        
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

async def process_wallet_with_specific_quests(wallet, quest_list):
    """Обрабатывает указанные задания для одного кошелька с интеграцией Twitter"""
    try:
        logger.info(f'Начинаю работу с {wallet} для заданий: {", ".join(quest_list)}')
        
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)
        
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
        twitter_min_delay, twitter_max_delay = settings.get_twitter_quest_delay()
        
        # Комбинируем задания в случайном порядке
        if twitter_enabled and twitter_quests:
            # Смешиваем задания
            all_quests = [("regular", quest) for quest in regular_quests] + [("twitter", quest) for quest in twitter_quests]
            random.shuffle(all_quests)
        else:
            # Если Twitter отключен, используем только обычные задания
            all_quests = [("regular", quest) for quest in regular_quests]
        
        # Выполняем задания в смешанном порядке
        for quest_type, quest_name in all_quests:
            try:
                result = None
                if quest_type == "regular":
                    # Выполняем обычное задание
                    logger.info(f"{wallet} выполняю задание {quest_name}")
                    result = await camp_client.quest_client.complete_quest(quest_name)
                    
                    if result:
                        logger.success(f"{wallet} успешно выполнено задание {quest_name}")
                    else:
                        logger.warning(f"{wallet} не удалось выполнить задание {quest_name}")
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(regular_min_delay, regular_max_delay))
                else:
                    # Выполняем Twitter задание
                    logger.info(f"{wallet} выполняю Twitter задание {quest_name}")
                    
                    # Создаем Twitter клиент и выполняем задание
                    twitter_manager = TwitterQuestManager(
                        user=wallet,
                        auth_client=camp_client.auth_client,
                        twitter_auth_token=wallet.twitter_token
                    )
                    
                    if "Follow" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=["CampNetwork", "campnetworkxyz"],
                            custom_tweet_text=None,
                            custom_tweet_to_like=None,
                            custom_tweet_to_retweet=None
                        )
                    elif "Tweet" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=None,
                            custom_tweet_text="Excited to be exploring @CampNetwork! Amazing project with great potential. #CampNetwork #Web3 #Crypto " + str(random.randint(1000, 9999)),
                            custom_tweet_to_like=None,
                            custom_tweet_to_retweet=None
                        )
                    elif "Like" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=None,
                            custom_tweet_text=None,
                            custom_tweet_to_like=1234567890123456789,  # Замените на реальный ID
                            custom_tweet_to_retweet=None
                        )
                    elif "Retweet" in quest_name:
                        result = await twitter_manager.complete_twitter_quests(
                            custom_follow_accounts=None,
                            custom_tweet_text=None,
                            custom_tweet_to_like=None,
                            custom_tweet_to_retweet=1234567890123456789  # Замените на реальный ID
                        )
                    
                    # Проверяем результат выполнения
                    if result:
                        logger.success(f"{wallet} успешно выполнено Twitter задание {quest_name}")
                    else:
                        logger.warning(f"{wallet} не удалось выполнить Twitter задание {quest_name}")
                    
                    # Задержка между Twitter заданиями
                    await asyncio.sleep(random.uniform(twitter_min_delay, twitter_max_delay))
            
            except Exception as e:
                logger.error(f"{wallet} ошибка при выполнении задания {quest_name}: {str(e)}")
                # Продолжаем с следующим заданием
                await asyncio.sleep(random.uniform(regular_max_delay, twitter_min_delay))
                continue
        
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

async def complete_specific_quests():
    """Выполняет указанные задания для всех кошельков с учетом настроек"""
    try:
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()
        
        if not all_wallets:
            logger.error("Нет кошельков в базе данных")
            return
        
        # Определяем диапазон кошельков для обработки
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]
        
        # Перемешиваем кошельки для рандомизации
        random.shuffle(wallets)
        
        logger.info(f"Найдено {len(all_wallets)} кошельков, обрабатываю {len(wallets)} из них")
        
        # Получаем список доступных заданий
        quests = list(QuestClient.QUEST_IDS.keys())
        
        # Если Twitter включен, добавляем Twitter задания
        if settings.twitter_enabled:
            quests.extend(["TwitterFollow", "TwitterTweet", "TwitterLike", "TwitterRetweet"])
        
        print("Доступные задания:")
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
        for wallet in wallets:
            # Добавляем случайную задержку между запуском обработки кошельков
            await asyncio.sleep(random.uniform(startup_min, startup_max))
            
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
        error_count = sum(1 for result in results if isinstance(result, Exception))
        logger.info(f"Обработка завершена: успешно {success_count}, с ошибками {error_count}")
        
    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")

async def get_wallets_stats():
    """Получает статистику по всем кошелькам из базы данных, включая Twitter интеграцию"""
    try:
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
        logger.info("Статистика кошельков:")
        for wallet_key, wallet_stats in stats.items():
            if "error" in wallet_stats:
                logger.warning(f"{wallet_key}: {wallet_stats['error']}")
            else:
                logger.info(f"{wallet_key}: {wallet_stats['completed_count']}/{wallet_stats['total_count']} заданий, Twitter: {wallet_stats['twitter_status']}")
                if wallet_stats['completed_count'] > 0:
                    logger.info(f"  Выполненные задания: {', '.join(wallet_stats['completed_quests'])}")
                
        return stats
            
    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return {}

