import asyncio
import random
from typing import Dict, List, Optional, Union, Any
from loguru import logger
import twitter  # Import tweepy-self library
from twitter.utils import remove_at_sign
from utils.db_api_async.models import User
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from website.http_client import BaseHttpClient
from data.config import CAPMONSTER_API_KEY


class TwitterClient(BaseHttpClient):
    """Клиент для взаимодействия с Twitter через tweepy-self"""

    # URL для запросов на выполнение квестов с Twitter
    BASE_URL = "https://loyalty.campnetwork.xyz"
    TWITTER_CONNECT_URL = f"{BASE_URL}/api/loyalty/social/connect/twitter"
    TWITTER_VERIFY_URL = f"{BASE_URL}/api/loyalty/social/verify/twitter"

    # ID квестов, связанных с Twitter
    TWITTER_QUEST_IDS = {
        # Add Twitter-related quest IDs from QUEST_IDS dictionary
        # For example: "TwitterFollow": "quest-id-from-quest-client"
    }

    def __init__(self, user: User, twitter_auth_token: str | None = None, twitter_username: str | None = None, 
                 twitter_password: str | None = None, totp_secret: str | None = None,):
        """
        Инициализация Twitter клиента
        
        Args:
            user: Объект пользователя
            twitter_auth_token: Токен авторизации Twitter
            twitter_username: Имя пользователя Twitter (без @)
            twitter_password: Пароль от аккаунта Twitter
            totp_secret: Секрет TOTP (если включена 2FA)
            capsolver_api_key: API ключ для сервиса CapSolver
        """
        super().__init__(user=user)
        
        # Создаем аккаунт Twitter
        self.twitter_account = twitter.Account(
            auth_token=twitter_auth_token,
            username=twitter_username,
            password=twitter_password,
            totp_secret=totp_secret
        )
        
        # Настройки для клиента Twitter
        self.client_config = {
            "wait_on_rate_limit": True,
            "auto_relogin": True,
            "update_account_info_on_startup": True,
            "capsolver_api_key": CAPMONSTER_API_KEY,
        }
        
        # Добавляем прокси, если оно указано
        if user.proxy:
            self.client_config["proxy"] = user.proxy
            
        # Статус соединения Twitter с CampNetwork
        self.is_connected = False
        self.twitter_client = None
        
    async def initialize(self) -> bool:
        """
        Инициализирует клиент Twitter
        
        Returns:
            Статус успеха
        """
        try:
            # Создаем клиент Twitter
            self.twitter_client = twitter.Client(self.twitter_account, **self.client_config)
            
            # Устанавливаем соединение
            await self.twitter_client.__aenter__()
            
            # Проверяем статус аккаунта
            await self.twitter_client.establish_status()
            
            if self.twitter_account.status == twitter.AccountStatus.GOOD:
                logger.success(f"{self.user} успешно инициализирован Twitter клиент @{self.twitter_account.username}")
                return True
            else:
                logger.error(f"{self.user} проблема со статусом Twitter аккаунта: {self.twitter_account.status}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при инициализации Twitter клиента: {str(e)}")
            return False
    
    async def close(self):
        """Закрывает соединение с Twitter"""
        if self.twitter_client:
            try:
                await self.twitter_client.__aexit__(None, None, None)
                self.twitter_client = None
            except Exception as e:
                logger.error(f"{self.user} ошибка при закрытии Twitter клиента: {str(e)}")
    
    async def __aenter__(self):
        """Контекстный менеджер для входа"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер для выхода"""
        await self.close()
    
    async def connect_twitter_to_camp(self) -> bool:
        """
        Подключает Twitter к CampNetwork
        
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка подключить Twitter без инициализации клиента")
            return False
            
        try:
            # 1. Запрос на создание соединения
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Origin': 'https://loyalty.campnetwork.xyz',
            })
            
            # Отправляем запрос на подключение Twitter
            success, response = await self.request(
                url=self.TWITTER_CONNECT_URL,
                method="POST",
                json_data={
                    "provider": "twitter",
                    "auth_token": self.twitter_account.auth_token,
                    "username": self.twitter_account.username
                },
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} успешно подключил Twitter к CampNetwork")
                self.is_connected = True
                return True
            else:
                logger.error(f"{self.user} не удалось подключить Twitter к CampNetwork: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при подключении Twitter к CampNetwork: {str(e)}")
            return False
    
    async def verify_twitter_connection(self) -> bool:
        """
        Проверяет соединение Twitter с CampNetwork
        
        Returns:
            Статус соединения
        """
        try:
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Origin': 'https://loyalty.campnetwork.xyz',
            })
            
            # Отправляем запрос на проверку соединения
            success, response = await self.request(
                url=self.TWITTER_VERIFY_URL,
                method="GET",
                headers=headers
            )
            
            if success and isinstance(response, dict) and response.get("connected") is True:
                logger.info(f"{self.user} Twitter подключен к CampNetwork")
                self.is_connected = True
                return True
            else:
                logger.warning(f"{self.user} Twitter не подключен к CampNetwork")
                self.is_connected = False
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при проверке соединения Twitter: {str(e)}")
            return False
    
    async def follow_account(self, account_name: str) -> bool:
        """
        Подписывается на указанный аккаунт в Twitter
        
        Args:
            account_name: Имя аккаунта для подписки (с @ или без)
            
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return False
            
        try:
            # Убираем @ из имени аккаунта, если он есть
            clean_account_name = remove_at_sign(account_name)
            
            # Получаем пользователя по имени
            user = await self.twitter_client.request_user_by_username(clean_account_name)
            
            if not user:
                logger.error(f"{self.user} не удалось найти пользователя @{clean_account_name}")
                return False
                
            # Подписываемся на пользователя
            is_followed = await self.twitter_client.follow(user.id)
            
            if is_followed:
                logger.success(f"{self.user} успешно подписался на @{clean_account_name}")
                return True
            else:
                logger.warning(f"{self.user} не удалось подписаться на @{clean_account_name}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при подписке на @{account_name}: {str(e)}")
            return False
    
    async def follow_accounts(self, account_names: List[str]) -> Dict[str, bool]:
        """
        Подписывается на указанные аккаунты в Twitter
        
        Args:
            account_names: Список имен аккаунтов для подписки
            
        Returns:
            Словарь результатов подписки на каждый аккаунт
        """
        results = {}
        
        for account_name in account_names:
            # Добавляем случайную задержку между подписками
            await asyncio.sleep(random.uniform(2.0, 5.0))
            
            result = await self.follow_account(account_name)
            results[account_name] = result
            
            # Если не удалось подписаться, делаем паузу подольше
            if not result:
                await asyncio.sleep(random.uniform(10.0, 15.0))
        
        # Общий результат
        success_count = sum(1 for result in results.values() if result)
        logger.info(f"{self.user} выполнено {success_count} из {len(results)} подписок")
        
        return results
        
    async def post_tweet(self, text: str) -> Optional[Any]:
        """
        Публикует твит с указанным текстом
        
        Args:
            text: Текст твита
            
        Returns:
            Объект твита в случае успеха, None в случае ошибки
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return None
            
        try:
            # Публикуем твит
            tweet = await self.twitter_client.tweet(text)
            
            if tweet:
                logger.success(f"{self.user} успешно опубликовал твит: {text[:30]}... (ID: {tweet.id})")
                return tweet
            else:
                logger.warning(f"{self.user} не удалось опубликовать твит")
                return None
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при публикации твита: {str(e)}")
            return None
    
    async def retweet(self, tweet_id: int) -> bool:
        """
        Ретвитит указанный твит
        
        Args:
            tweet_id: ID твита для ретвита
            
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return False
            
        try:
            # Делаем ретвит
            retweet_id = await self.twitter_client.repost(tweet_id)
            
            if retweet_id:
                logger.success(f"{self.user} успешно сделал ретвит твита {tweet_id}")
                return True
            else:
                logger.warning(f"{self.user} не удалось сделать ретвит твита {tweet_id}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при ретвите твита {tweet_id}: {str(e)}")
            return False
    
    async def like_tweet(self, tweet_id: int) -> bool:
        """
        Ставит лайк указанному твиту
        
        Args:
            tweet_id: ID твита для лайка
            
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return False
            
        try:
            # Ставим лайк
            is_liked = await self.twitter_client.like(tweet_id)
            
            if is_liked:
                logger.success(f"{self.user} успешно поставил лайк твиту {tweet_id}")
                return True
            else:
                logger.warning(f"{self.user} не удалось поставить лайк твиту {tweet_id}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при лайке твита {tweet_id}: {str(e)}")
            return False
    
    async def complete_twitter_quest(self, quest_name: str, target_accounts: List[str] | None = None, 
                                     tweet_text: str | None = None, tweet_id_to_like: int | None = None, 
                                     tweet_id_to_retweet: int | None = None) -> bool:
        """
        Выполняет задание Twitter по его названию
        
        Args:
            quest_name: Название задания
            target_accounts: Список аккаунтов для подписки
            tweet_text: Текст твита для публикации
            tweet_id_to_like: ID твита для лайка
            tweet_id_to_retweet: ID твита для ретвита
            
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить задание без инициализации клиента")
            return False
            
        try:
            # Проверяем, подключен ли Twitter к CampNetwork
            if not self.is_connected:
                is_verified = await self.verify_twitter_connection()
                if not is_verified:
                    logger.info(f"{self.user} Twitter не подключен к CampNetwork, подключаем...")
                    if not await self.connect_twitter_to_camp():
                        logger.error(f"{self.user} не удалось подключить Twitter к CampNetwork")
                        return False
            
            # Выполняем действия в зависимости от задания
            quest_success = False
            
            # Задание на подписку
            if "Follow" in quest_name and target_accounts:
                follow_results = await self.follow_accounts(target_accounts)
                quest_success = any(follow_results.values())
            
            # Задание на публикацию твита
            elif "Tweet" in quest_name and tweet_text:
                tweet = await self.post_tweet(tweet_text)
                quest_success = tweet is not None
            
            # Задание на лайк
            elif "Like" in quest_name and tweet_id_to_like:
                quest_success = await self.like_tweet(tweet_id_to_like)
            
            # Задание на ретвит
            elif "Retweet" in quest_name and tweet_id_to_retweet:
                quest_success = await self.retweet(tweet_id_to_retweet)
            
            # После выполнения действий в Twitter, отправляем запрос на сервер CampNetwork
            if quest_success:
                # Получаем ID задания
                quest_id = self.TWITTER_QUEST_IDS.get(quest_name)
                if not quest_id:
                    logger.error(f"{self.user} задание {quest_name} не найдено в списке")
                    return False
                
                # Формируем URL для запроса на выполнение задания
                complete_url = f"{self.BASE_URL}/api/loyalty/rules/{quest_id}/complete"
                
                headers = await self.get_headers({
                    'Content-Type': 'application/json',
                    'Origin': 'https://loyalty.campnetwork.xyz',
                })
                
                # Отправляем запрос на выполнение задания
                success, response = await self.request(
                    url=complete_url,
                    method="POST",
                    json_data={},  # Пустой JSON как в quest_client
                    headers=headers
                )
                
                if success:
                    logger.success(f"{self.user} успешно выполнил Twitter задание {quest_name}")
                    
                    # Отмечаем задание как выполненное в БД
                    try:
                        async with Session() as session:
                            db = DB(session=session)
                            await db.mark_quest_completed(self.user.id, quest_id)
                    except Exception as e:
                        logger.error(f"{self.user} ошибка при сохранении статуса задания в БД: {e}")
                    
                    return True
                
                else:
                    # Проверка на "You have already been rewarded"
                    if isinstance(response, dict) and response.get("message") == "You have already been rewarded" and response.get("rewarded") is True:
                        logger.info(f"{self.user} задание {quest_name} уже выполнено ранее")
                        
                        # Отмечаем задание как выполненное в БД
                        try:
                            async with Session() as session:
                                db = DB(session=session)
                                await db.mark_quest_completed(self.user.id, quest_id)
                        except Exception as e:
                            logger.error(f"{self.user} ошибка при сохранении статуса задания в БД: {e}")
                        
                        return True
                    else:
                        logger.error(f"{self.user} ошибка при выполнении задания {quest_name}: {response}")
                        return False
            
            else:
                logger.error(f"{self.user} не удалось выполнить действия в Twitter для задания {quest_name}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при выполнении Twitter задания {quest_name}: {str(e)}")
            return False


class TwitterQuestManager:
    """Менеджер заданий Twitter для CampNetwork"""

    # Список аккаунтов для подписки по умолчанию
    DEFAULT_FOLLOW_ACCOUNTS = [
        "test",
        # Добавьте другие аккаунты по необходимости
    ]
    
    # Шаблоны твитов по умолчанию
    DEFAULT_TWEET_TEMPLATES = [
        "Just discovered @CampNetwork! Amazing platform for web3 enthusiasts. #CampNetwork #Web3",
        "Excited to be part of the @CampNetwork community! #CampNetwork #Crypto",
        "Checking out @CampNetwork - a game-changer in the web3 space. #CampNetwork #Blockchain"
    ]
    
    # ID и URL для твитов, которые нужно лайкнуть/ретвитнуть по умолчанию
    DEFAULT_TWEETS_TO_LIKE = [
        1234567890123456789, # Замените на реальный ID твита
    ]
    
    DEFAULT_TWEETS_TO_RETWEET = [
        1231,
    ]
    
    def __init__(self, user: User, twitter_auth_token: str, twitter_username: str | None = None, 
                 twitter_password: str | None = None, totp_secret: str | None = None, capsolver_api_key: str | None = None):
        """
        Инициализация менеджера заданий Twitter
        
        Args:
            user: Объект пользователя
            twitter_auth_token: Токен авторизации Twitter
            twitter_username: Имя пользователя Twitter
            twitter_password: Пароль Twitter
            totp_secret: Секрет TOTP (если включена 2FA)
            capsolver_api_key: API ключ для сервиса CapSolver
        """
        self.user = user
        self.twitter_auth_token = twitter_auth_token
        self.twitter_username = twitter_username
        self.twitter_password = twitter_password
        self.totp_secret = totp_secret
        self.capsolver_api_key = capsolver_api_key
        
    async def complete_twitter_quests(self, custom_follow_accounts: List[str] | None = None, 
                                     custom_tweet_text: str | None = None, 
                                     custom_tweet_to_like: int | None = None,
                                     custom_tweet_to_retweet: int | None = None) -> Dict[str, bool] | bool:
        """
        Выполняет все задания Twitter
        
        Args:
            custom_follow_accounts: Кастомный список аккаунтов для подписки
            custom_tweet_text: Кастомный текст твита
            custom_tweet_to_like: Кастомный ID твита для лайка
            custom_tweet_to_retweet: Кастомный ID твита для ретвита
            
        Returns:
            Результаты выполнения заданий
        """
        results = {}
        
        # Определяем данные для заданий
        follow_accounts = custom_follow_accounts or self.DEFAULT_FOLLOW_ACCOUNTS
        
        # Выбираем случайный шаблон твита, если не указан кастомный
        if not custom_tweet_text and self.DEFAULT_TWEET_TEMPLATES:
            tweet_text = random.choice(self.DEFAULT_TWEET_TEMPLATES)
        else:
            tweet_text = custom_tweet_text
            
        # Выбираем случайный твит для лайка, если не указан кастомный
        if not custom_tweet_to_like and self.DEFAULT_TWEETS_TO_LIKE:
            tweet_to_like = random.choice(self.DEFAULT_TWEETS_TO_LIKE)
        else:
            tweet_to_like = custom_tweet_to_like
            
        # Выбираем случайный твит для ретвита, если не указан кастомный
        if not custom_tweet_to_retweet and self.DEFAULT_TWEETS_TO_RETWEET:
            tweet_to_retweet = random.choice(self.DEFAULT_TWEETS_TO_RETWEET)
        else:
            tweet_to_retweet = custom_tweet_to_retweet
        
        try:
            logger.info(f"{self.user} начинаем выполнение Twitter заданий")
            
            # Создаем клиент Twitter
            async with TwitterClient(
                user=self.user,
                twitter_auth_token=self.twitter_auth_token,
                twitter_username=self.twitter_username,
                twitter_password=self.twitter_password,
                totp_secret=self.totp_secret,
            ) as twitter_client:
                
                # Проверяем, инициализирован ли клиент
                if not twitter_client.twitter_client:
                    logger.error(f"{self.user} не удалось инициализировать Twitter клиент")
                    return {"initialisation": False}
                
                # Выполняем задание подписки
                if follow_accounts:
                    results["TwitterFollow"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterFollow",
                        target_accounts=follow_accounts
                    )
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(5.0, 10.0))
                
                # Выполняем задание публикации твита
                if tweet_text:
                    results["TwitterTweet"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterTweet",
                        tweet_text=tweet_text
                    )
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(5.0, 10.0))
                
                # Выполняем задание лайка
                if tweet_to_like:
                    results["TwitterLike"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterLike",
                        tweet_id_to_like=tweet_to_like
                    )
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(5.0, 10.0))
                
                # Выполняем задание ретвита
                if tweet_to_retweet:
                    results["TwitterRetweet"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterRetweet",
                        tweet_id_to_retweet=tweet_to_retweet
                    )
            
            # Подсчитываем результаты
            success_count = sum(1 for result in results.values() if result)
            logger.success(f"{self.user} выполнено {success_count} из {len(results)} Twitter заданий")
            
            return results
            
        except Exception as e:
            logger.error(f"{self.user} ошибка при выполнении Twitter заданий: {str(e)}")
            return False 
