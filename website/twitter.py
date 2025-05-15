import asyncio
import jwt
import string
import time
import random
from typing import Dict, List, Optional, Union, Any
from loguru import logger
import twitter  # Import tweepy-self library
from twitter.utils import remove_at_sign
from utils.db_api_async.models import User
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from website.http_client import BaseHttpClient
from website.camp_client import CampNetworkClient
from data.config import CAPMONSTER_API_KEY
from data.models import Settings


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

    def __init__(self, user: User, auth_client, twitter_auth_token: str, twitter_username: str | None = None, 
                 twitter_password: str | None = None, totp_secret: str | None = None):
        """
        Инициализация Twitter клиента
        
        Args:
            user: Объект пользователя
            auth_client: Авторизованный клиент для CampNetwork
            twitter_auth_token: Токен авторизации Twitter
            twitter_username: Имя пользователя Twitter (без @)
            twitter_password: Пароль от аккаунта Twitter
            totp_secret: Секрет TOTP (если включена 2FA)
        """
        super().__init__(user=user)
        
        # Сохраняем auth_client для использования в запросах к CampNetwork
        self.auth_client = auth_client
        
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
        Подключает Twitter к CampNetwork с использованием существующего auth_client
        
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка подключить Twitter без инициализации клиента")
            return False
            
        try:
            # Проверяем, что у нас есть auth_client и что пользователь авторизован
            if not hasattr(self, 'auth_client') or not self.auth_client.user_id:
                logger.error(f"{self.user} отсутствует auth_client или пользователь не авторизован")
                return False
            
            # Шаг 1: Делаем запрос к /api/twitter/auth для получения параметров авторизации Twitter
            logger.info(f"{self.user} запрашиваю параметры авторизации Twitter")
            
            headers = await self.auth_client.get_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://loyalty.campnetwork.xyz/home',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
            })
            
            # Используем auth_client для запроса, но указываем не следовать редиректам
            auth_success, auth_response = await self.auth_client.request(
                url="https://loyalty.campnetwork.xyz/api/twitter/auth",
                method="GET",
                headers=headers,
                allow_redirects=False  # Добавим этот параметр в метод request
            )
            
            # Проверяем, получили ли мы ответ с редиректом
            # auth_response может быть либо словарем заголовков, либо содержимым ответа
            if 'Location' in auth_response:
                # Извлекаем URL из Location header
                twitter_auth_url = auth_response['Location']
                logger.info(f"{self.user} получен URL авторизации Twitter: {twitter_auth_url}")
                
                # Парсим URL для извлечения параметров
                import urllib.parse
                parsed_url = urllib.parse.urlparse(twitter_auth_url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                # Извлекаем необходимые параметры
                state = query_params.get('state', [''])[0]
                code_challenge = query_params.get('code_challenge', [''])[0]
                client_id = query_params.get('client_id', ['TVBRYlFuNzg5RVo4QU11b3EzVV86MTpjaQ'])[0]
                redirect_uri = query_params.get('redirect_uri', ['https://snag-render.com/api/twitter/auth/callback'])[0]
                
                if not state or not code_challenge:
                    logger.error(f"{self.user} не удалось извлечь необходимые параметры из URL авторизации")
                    return False
                    
                logger.info(f"{self.user} извлечены параметры: state={state[:20]}..., code_challenge={code_challenge}")
                
                # Шаг 2: Используем параметры для OAuth2 авторизации Twitter
                oauth2_data = {
                    'response_type': 'code',
                    'client_id': client_id,
                    'redirect_uri': redirect_uri,
                    'scope': 'users.read tweet.read',
                    'state': state,
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'plain'
                }
                
                logger.info(f"{self.user} выполняю OAuth2 запрос к Twitter")
                
                # Выполняем OAuth2 авторизацию
                auth_code = await self.twitter_client.oauth2(**oauth2_data)
                
                if not auth_code:
                    logger.error(f"{self.user} не удалось получить код авторизации от Twitter")
                    return False
                    
                logger.success(f"{self.user} успешно получен код авторизации: {auth_code}")
                
                # Шаг 3: Делаем запрос на callback URL
                # Для этого шага используем обычный HTTP клиент, так как нам не нужно сохранять состояние
                callback_url = f"{redirect_uri}?state={state}&code={auth_code}"
                logger.info(f"{self.user} выполняю запрос на callback URL: {callback_url}")
                
                callback_headers = {
                    'User-Agent': self.user.user_agent,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer': 'https://x.com/',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'cross-site',
                }
                
                # Используем метод запроса из BaseHttpClient, так как мы уже наследуемся от него
                callback_success, callback_response = await self.request(
                    url=callback_url,
                    method="GET",
                    headers=callback_headers,
                    allow_redirects=False,
                )
                
                # Проверяем, получили ли мы редирект на connect URL
                if not callback_success and isinstance(callback_response, dict) and 'Location' in callback_response:
                    connect_url = callback_response['Location']
                    logger.info(f"{self.user} выполняю запрос на подключение Twitter: {connect_url}")
                    
                    # Шаг 4: Выполняем запрос на подключение Twitter
                    # Важно: используем auth_client для этого запроса, чтобы использовать его куки и сессию
                    connect_headers = await self.auth_client.get_headers({
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Referer': 'https://x.com/',
                        'DNT': '1',
                        'Sec-GPC': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'cross-site',
                        'Sec-Fetch-User': '?1',
                        'Priority': 'u=0, i',
                    })
                    
                    # Используем auth_client.request для запроса, чтобы использовать его куки

                    connect_success, connect_response = await self.auth_client.request(
                        url=connect_url,
                        method="GET",
                        headers=connect_headers,
                        allow_redirects=False  # Следуем за всеми редиректами
                    )
                    
                    # Проверяем результат подключения
                    # В этом случае, success может быть True, если мы получили 200 после всех редиректов
                    if connect_success:
                        logger.success(f"{self.user} успешно подключил Twitter к CampNetwork")
                        return True
                    else:
                        # Проверяем, получили ли мы редирект на основную страницу
                        if isinstance(connect_response, dict) and 'Location' in connect_response and 'loyalty.campnetwork.xyz/loyalty' in connect_response['Location']:
                            logger.success(f"{self.user} успешно подключил Twitter к CampNetwork (редирект на loyalty)")
                            return True
                        
                        logger.error(f"{self.user} ошибка при подключении Twitter: {connect_response}")
                        return False
                else:
                    logger.error(f"{self.user} не получен ожидаемый редирект от callback URL: {callback_response}")
                    return False
            else:
                logger.error(f"{self.user} не удалось получить редирект на авторизацию Twitter: {auth_response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при подключении Twitter к CampNetwork: {str(e)}")
            return False

    async def check_twitter_connection_status(self,) -> bool:
        """
        Проверяет, подключен ли Twitter к аккаунту CampNetwork
        
        Args:
            wallet_address: Адрес кошелька
            
        Returns:
            True если Twitter подключен, False в противном случае
        """
        try:
            # Формируем URL с параметрами
            url = f"{self.BASE_URL}/api/users"
            params = {
                "walletAddress": self.user.public_key,
                "includeDelegation": "false",
                "websiteId": "32afc5c9-f0fb-4938-9572-775dee0b4a2b",
                "organizationId": "26a1764f-5637-425e-89fa-2f3fb86e758c"
            }
            
            headers = await self.auth_client.get_headers({
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://loyalty.campnetwork.xyz/loyalty',
            })
            
            # Отправляем запрос
            success, response = await self.auth_client.request(
                url=url,
                method="GET",
                params=params,
                headers=headers
            )
            
            if success and isinstance(response, dict) and "data" in response:
                # Проверяем наличие Twitter-аккаунта в данных пользователя
                user_data = response.get("data", [])[0] if response.get("data") else None
                
                if user_data and "userMetadata" in user_data:
                    user_metadata = user_data["userMetadata"][0] if user_data["userMetadata"] else None
                    
                    if user_metadata:
                        twitter_user = user_metadata.get("twitterUser")
                        twitter_verified_at = user_metadata.get("twitterVerifiedAt")
                        
                        if twitter_user and twitter_verified_at:
                            logger.success(f"{self.user} Twitter уже подключен (@{twitter_user})")
                            return True
            
            logger.info(f"{self.user} Twitter не подключен к аккаунту")
            return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при проверке статуса подключения Twitter: {str(e)}")
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
        
        # Получаем настройки задержек
        settings = Settings()
        min_delay, max_delay = settings.get_twitter_action_delay()
        
        for account_name in account_names:
            # Добавляем случайную задержку между подписками
            await asyncio.sleep(random.uniform(min_delay, max_delay))
            
            result = await self.follow_account(account_name)
            results[account_name] = result
            
            # Если не удалось подписаться, делаем паузу подольше
            if not result:
                await asyncio.sleep(random.uniform(min_delay * 2, max_delay * 2))
        
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
    
    def __init__(self, user: User, auth_client, twitter_auth_token: str, twitter_username: str | None = None, 
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
        self.auth_client = auth_client
        

    async def ensure_authorized(self) -> tuple:
        """
        Проверяет авторизацию на сайте CampNetwork и выполняет её при необходимости
        
        Returns:
            (success, auth_client): Статус успеха и авторизованный клиент
        """
        try:
            # Создаем клиент CampNetwork для авторизации
            camp_client = CampNetworkClient(user=self.user)
            
            # Выполняем авторизацию
            logger.info(f"{self.user} выполняю авторизацию на CampNetwork")
            auth_success = await camp_client.login()
            
            if not auth_success:
                logger.error(f"{self.user} не удалось авторизоваться на CampNetwork")
                return False, None
                
            logger.success(f"{self.user} успешно авторизован на CampNetwork")
            return True, camp_client.auth_client
            
        except Exception as e:
            logger.error(f"{self.user} ошибка при авторизации на CampNetwork: {str(e)}")
            return False, None

    async def complete_twitter_quests(self, custom_follow_accounts: List[str] | None = None, 
                                     custom_tweet_text: str | None = None, 
                                     custom_tweet_to_like: int | None = None,
                                     custom_tweet_to_retweet: int | None = None) -> bool:
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
        
        # Получаем настройки задержек
        settings = Settings()
        min_quest_delay, max_quest_delay = settings.get_twitter_quest_delay()
        
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
            auth_success, auth_client = await self.ensure_authorized()
            logger.info(f"{self.user} начинаем выполнение Twitter заданий")
            if not auth_success or not auth_client:
                logger.error(f"{self.user} невозможно выполнить Twitter задания без авторизации")
                return False
            # Создаем клиент Twitter
            async with TwitterClient(
                user=self.user,
                auth_client=auth_client,
                twitter_auth_token=self.twitter_auth_token,
                twitter_username=self.twitter_username,
                twitter_password=self.twitter_password,
                totp_secret=self.totp_secret,
            ) as twitter_client:
                
                # Проверяем, инициализирован ли клиент
                if not twitter_client.twitter_client:
                    logger.error(f"{self.user} не удалось инициализировать Twitter клиент")
                    return False

                if not twitter_client.is_connected:
                    is_verified = await twitter_client.check_twitter_connection_status()
                    if not is_verified:
                        logger.info(f"{self.user} Twitter не подключен к CampNetwork, подключаем...")
                        if not await twitter_client.connect_twitter_to_camp():
                            logger.error(f"{self.user} не удалось подключить Twitter к CampNetwork")
                            return False
                # Выполняем задание подписки
                if follow_accounts:
                    results["TwitterFollow"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterFollow",
                        target_accounts=follow_accounts
                    )
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(min_quest_delay, max_quest_delay))
                
                # Выполняем задание публикации твита
                if tweet_text:
                    results["TwitterTweet"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterTweet",
                        tweet_text=tweet_text
                    )
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(min_quest_delay, max_quest_delay))
                
                # Выполняем задание лайка
                if tweet_to_like:
                    results["TwitterLike"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterLike",
                        tweet_id_to_like=tweet_to_like
                    )
                    
                    # Задержка между заданиями
                    await asyncio.sleep(random.uniform(min_quest_delay, max_quest_delay))
                
                # Выполняем задание ретвита
                if tweet_to_retweet:
                    results["TwitterRetweet"] = await twitter_client.complete_twitter_quest(
                        quest_name="TwitterRetweet",
                        tweet_id_to_retweet=tweet_to_retweet
                    )
            
            # Подсчитываем результаты
            success_count = sum(1 for result in results.values() if result)
            logger.success(f"{self.user} выполнено {success_count} из {len(results)} Twitter заданий")
            
            return True
            
        except Exception as e:
            logger.error(f"{self.user} ошибка при выполнении Twitter заданий: {str(e)}")
            return False
