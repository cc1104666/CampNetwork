import aiohttp
import asyncio
import json
import datetime
import random
import re
import functools
from urllib.parse import urlparse
from loguru import logger
from aiohttp import ClientSession 
from utils.db_api_async.models import User
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from libs.eth_async.client import Client
from eth_account.messages import encode_defunct
from data.config import CAPMONSTER_API_KEY, TWOCAPTCHA_API_KEY

GET = "get"
POST = "post"
DELETE = "delete"
PUT = "put"

def error_handler(func):
    """Декоратор для обработки ошибок в асинхронных методах"""
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except aiohttp.ClientConnectionError as e:
            logger.error(f'{self.website.user if hasattr(self, "website") else self.user} ошибка соединения: {str(e)}')
            return False, None
        except Exception as e:
            logger.error(f'{self.website.user if hasattr(self, "website") else self.user} ошибка запроса: {str(e)}')
            return False, None
    return wrapper


class CloudflareHandler:
    """Обработчик Cloudflare Turnstile защиты"""
    
    def __init__(self, website):
        self.website = website
    
    async def parse_proxy(self):
        """Парсит прокси строку в более удобный формат"""
        if not self.website.user.proxy:
            return None, None, None, None
            
        parsed = urlparse(self.website.user.proxy)
        
        ip = parsed.hostname
        port = parsed.port
        login = parsed.username
        password = parsed.password
        
        return ip, port, login, password
    
    async def recaptcha_handle(self, session, html: str):
        """Обрабатывает Cloudflare Turnstile captcha через CapMonster"""
        max_retry = 10
        captcha_token = None
        retry_delay = 2  # начальная задержка в секундах
        await asyncio.sleep(random.randint(1, 10)) 
        for i in range(max_retry):
            try:
                # Получаем задание на решение Turnstile
                task = await self.get_recaptcha_task(session=session, html=html)
                if not task:
                    logger.error(f'{self.website.user} не удалось создать задачу в CapMonster')
                    await asyncio.sleep(retry_delay)
                    i += 1
                    continue
                
                # Получаем результат решения
                result = await self.get_recaptcha_token(task_id=task, session=session)
                if result:
                    captcha_token = result
                    # logger.info(f'{self.website.user} получен token от CapMonster')
                    break
                else:
                    logger.warning(f'{self.website.user} не удалось получить token, повторная попытка')
                    await asyncio.sleep(random.randint(1, 10))
                    i += 1
                    continue
            except Exception as e:
                logger.error(f'{self.website.user} ошибка с get recaptcha token {e}')
                await asyncio.sleep(random.randint(1, 10))
                i += 1
                continue
                    
        return captcha_token

    async def get_recaptcha_task(self, session, html: str):
        """Создает задачу на решение Cloudflare в CapMonster"""
        try:
            # Парсинг прокси
            ip, port, login, password = await self.parse_proxy()
            cloudflare_html = html
            
            # Кодируем HTML в base64 как в JavaScript примере
            html_base64 = self.encode_html_to_base64(cloudflare_html)           
            windows_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            # Данные для запроса к CapMonster
            json_data = {
                "clientKey": CAPMONSTER_API_KEY,
                "task": {
                    "type": "TurnstileTask",
                    "websiteURL": "https://loyalty.campnetwork.xyz/home",
                    "websiteKey": "0x4AAAAAAADnPIDROrmt1Wwj",
                    "cloudflareTaskType": "cf_clearance",  # Нужен cf_clearance cookie
                    "htmlPageBase64": html_base64,
                    "userAgent": windows_user_agent
                }
            }
            
            # Добавляем данные прокси, если они есть
            if ip and port:
                json_data["task"].update({
                    "proxyType": "http",
                    "proxyAddress": ip,
                    "proxyPort": port
                })
                
                if login and password:
                    json_data["task"].update({
                        "proxyLogin": login,
                        "proxyPassword": password
                    })
            # Отправляем запрос на создание задачи
            async with session.request(method='POST', url='https://api.capmonster.cloud/createTask',
                                      json=json_data) as resp:
                if resp.status == 200:
                    result = await resp.text()
                    result = json.loads(result)
                    
                    if result.get('errorId') == 0:
                        return result['taskId']
                    else:
                        return False
                else:
                    logger.error(f'{self.website.user} ошибка запроса к CapMonster: {resp.status}, {await resp.text()}')
                    return False
        except Exception as e:
            logger.error(f'{self.website.user} ошибка при создании задачи в CapMonster: {str(e)}')
            return False

    def encode_html_to_base64(self, html_content):
        """
        Кодирует HTML в base64 по аналогии с JavaScript:
        var htmlBase64 = btoa(unescape(encodeURIComponent(htmlContent)))
        """
        import base64
        import urllib.parse
        
        # Эквивалент encodeURIComponent в JavaScript
        encoded = urllib.parse.quote(html_content)
        
        # Эквивалент unescape в JavaScript
        # (замена %xx последовательностей на соответствующие символы)
        unescaped = urllib.parse.unquote(encoded)
        
        # Эквивалент btoa в JavaScript
        base64_encoded = base64.b64encode(unescaped.encode('latin1')).decode('ascii')
        
        return base64_encoded

    async def get_recaptcha_token(self, task_id, session):
        """Получает результат решения задачи от CapMonster"""
        json_data = {
            "clientKey": CAPMONSTER_API_KEY,
            "taskId": task_id
        }
        
        # Максимальное время ожидания (30 секунд)
        max_attempts = 60
        
        for i in range(max_attempts):
            try:
                async with session.request(method='POST', url='https://api.capmonster.cloud/getTaskResult',
                                          json=json_data) as resp:
                    if resp.status == 200:
                        result = await resp.text()
                        result = json.loads(result)
                        
                        if result['status'] == 'ready':
                            # Получаем cf_clearance из решения
                            if 'solution' in result:
                                return result['solution'].get('cf_clearance') or result['solution'].get('token')
                            
                            return False
                        elif result['status'] == 'processing':
                            await asyncio.sleep(2)
                            continue
                        else:
                            return False
                    else:
                        await asyncio.sleep(2)
                        continue
            except Exception as e:
                logger.error(f'{self.website.user} ошибка при получении результата: {str(e)}')
                return False
                
        logger.error(f'{self.website.user} превышено время ожидания решения от CapMonster')
        return False

    # TODO: Fix get token. Maybe try SDK. Думаю проблема не в решении капчи, а в первом запросе на сайт
    async def handle_cloudflare_protection(self, method, **request_kwargs):
        """
        Обрабатывает защиту Cloudflare и возвращает cf_clearance
        
        Args:
            method: Метод запроса (GET, POST, etc.)
            request_kwargs: Дополнительные параметры запроса
            
        Returns:
            (bool, dict): Статус успеха и JSON-данные ответа
        """
        try:
            # Делаем начальный запрос
            async with getattr(self.website.session, method.lower())(**request_kwargs) as resp:
                # Сохраняем куки из ответа
                if resp.cookies:
                    for name, cookie in resp.cookies.items():
                        self.website.cookies[name] = cookie.value
                try:
                    json_data = await resp.json()
                except Exception:
                    json_data = {}
                
                # Проверяем на наличие Cloudflare
                if resp.status == 403:
                    response_text = await resp.text()
                    
                    if 'cloudflare' in response_text.lower() or 'turnstile' in response_text.lower() or 'challenge' in response_text.lower():
                        
                        # Решаем Cloudflare и получаем cf_clearance
                        cf_clearance = await self.recaptcha_handle(session=self.website.session, html=response_text)
                        
                        if cf_clearance:
                            # logger.info(f"{self.website.user} получен cf_clearance, повторяем запрос")
                            
                            # Добавляем cf_clearance в cookies
                            self.website.cookies['cf_clearance'] = cf_clearance
                            
                            # Обновляем user-agent на тот, с которым был получен cf_clearance
                            # Это критично для Cloudflare, cf_clearance привязан к User-Agent
                            windows_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
                            request_kwargs['headers']['User-Agent'] = windows_user_agent
                            
                            # Добавляем cookies в запрос
                            request_kwargs['cookies'] = self.website.cookies
                            
                            # Повторяем запрос с обновленными cookies
                            try:
                                async with getattr(self.website.session, method.lower())(**request_kwargs) as new_resp:
                                    # Сохраняем куки из ответа
                                    if new_resp.cookies:
                                        for name, cookie in new_resp.cookies.items():
                                            self.website.cookies[name] = cookie.value
                                    try:
                                        json_data = await new_resp.json()
                                        return True, json_data
                                    except Exception:
                                        return True, {}
                            except Exception as e:
                                logger.error(f'{self.website.user} ошибка при повторном запросе: {str(e)}')
                                return False, {}
                
                # Возвращаем исходный ответ, если не было Cloudflare или мы не смогли его обойти
                return True, json_data
        
        except Exception as e:
            logger.error(f'{self.website.user} ошибка при обработке Cloudflare: {str(e)}')
            return False, None


class HttpClient:
    """Базовый HTTP клиент для выполнения запросов"""
    
    def __init__(self, website):
        self.website = website
    
    def get_headers(self, additional_headers=None):
        """Создает базовые заголовки для запросов с возможностью добавления дополнительных"""
        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://loyalty.campnetwork.xyz/',
            'DNT': '1',
            'Sec-GPC': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
            'Priority': 'u=4',
        }
        
        if additional_headers:
            base_headers.update(additional_headers)
            
        return base_headers
    
    @error_handler
    async def request(self, url: str, method: str, data: dict | None = None, json_data: dict | None = None, 
                    params: dict | None = None, headers: dict | None = None, allow_redirects: bool = True,
                    handle_cloudflare: bool = False, timeout=30, retries=3):
        """
        Выполняет HTTP-запрос с возможностью обработки Cloudflare
        
        Args:
            url: URL для запроса
            method: Метод запроса (GET, POST, DELETE, PUT)
            data: Данные формы
            json_data: JSON данные
            params: URL параметры
            headers: HTTP заголовки
            allow_redirects: Разрешить перенаправления
            handle_cloudflare: Если True, при обнаружении Cloudflare попытается обойти защиту
            timeout: Тайм-аут запроса в секундах
            retries: Количество повторных попыток при сетевых ошибках
        
        Returns:
            (bool, data): Статус успеха и данные ответа (JSON или текст)
        """
        # Формируем базовые заголовки
        base_headers = self.get_headers(headers)
                
        # Базовые параметры запроса
        request_kwargs = {
            'url': url,
            'proxy': self.website.user.proxy,
            'headers': base_headers,
            'cookies': self.website.cookies,
            'allow_redirects': allow_redirects,
            'timeout': aiohttp.ClientTimeout(total=timeout)
        }
        
        # Добавляем параметры только если они предоставлены
        if json_data is not None:
            request_kwargs['json'] = json_data
        if data is not None:
            request_kwargs['data'] = data
        if params is not None:
            request_kwargs['params'] = params
        
        # Выполняем запрос с повторными попытками при ошибках
        for attempt in range(retries):
            try:
                # Обрабатываем Cloudflare, если это требуется
                if handle_cloudflare:
                    return await self.website.cloudflare.handle_cloudflare_protection(method, **request_kwargs)
                
                # Стандартный запрос без обработки Cloudflare
                async with getattr(self.website.session, method.lower())(**request_kwargs) as resp:
                    # Сохраняем куки из ответа
                    if resp.cookies:
                        for name, cookie in resp.cookies.items():
                            self.website.cookies[name] = cookie.value
                    
                    if resp.status == 200 or resp.status == 202:
                        try:
                            json_data = await resp.json()
                            return True, json_data
                        except Exception:
                            return True, await resp.text() 
                    
                    # Если статус не 200/202, но запрос выполнен без ошибок
                    if 400 <= resp.status < 500:
                        # Клиентские ошибки обычно не имеет смысла повторять
                        logger.warning(f'{self.website.user} получен статус {resp.status} при запросе {url}')
                        return False, await resp.text()
                    elif 500 <= resp.status < 600:
                        # Серверные ошибки можно повторить
                        logger.warning(f'{self.website.user} получен статус {resp.status} при запросе {url}, повторная попытка {attempt+1}/{retries}')
                        await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                        continue
                    
                    return False, await resp.text()
                    
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                # Сетевые ошибки или тайм-ауты - повторяем запрос
                logger.warning(f'{self.website.user} ошибка соединения при запросе {url}, повторная попытка {attempt+1}/{retries}: {str(e)}')
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                continue
            except Exception as e:
                logger.error(f'{self.website.user} неожиданная ошибка при запросе {url}: {str(e)}')
                return False, None
        
        # Если все попытки исчерпаны
        logger.error(f'{self.website.user} исчерпаны все попытки запроса {url}')
        return False, None


class AuthManager:
    """Управление аутентификацией и сессиями"""
    
    def __init__(self, website):
        self.website = website
    
    async def test_resp(self):
        url = 'https://loyalty.campnetwork.xyz/home'
        resp, json_data = await self.website.http.request(url=url, method=GET, handle_cloudflare = True)
        if resp:
            return True

    async def connect_wallet(self):
        """Первый этап авторизации - подключение кошелька через Dynamic Auth"""
        json_data = {
            'address': f'{self.website.user.public_key}',
            'chain': 'EVM',
            'provider': 'browserExtension',
            'walletName': 'rabby',
            'authMode': 'connect-only',
        }
        
        headers = self.website.http.get_headers({
            'Content-Type': 'application/json',
            'x-dyn-version': 'WalletKit/3.9.11',
            'x-dyn-api-version': 'API/0.0.586',
            'Origin': 'https://loyalty.campnetwork.xyz',
        })
        
        url = 'https://app.dynamicauth.com/api/v0/sdk/09a766ae-a662-4d96-904a-28d1c9e4b587/connect'
        resp, json_data = await self.website.http.request(url=url, method=POST, json_data=json_data, headers=headers)
        
        if resp: 
            # logger.info(f'{self.website.user} успешно подключил кошелек через Dynamic Auth')
            return True
        return False
    
    async def get_csrf_token(self):
        """Получение CSRF токена с автоматическим решением Cloudflare Turnstile при необходимости"""
        url = 'https://loyalty.campnetwork.xyz/api/auth/csrf'
        headers = self.website.http.get_headers({
            'Content-Type': 'application/json',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Origin': 'https://loyalty.campnetwork.xyz',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        # Включаем автоматическое решение Cloudflare Turnstile
        resp, json_data = await self.website.http.request(url=url, method=GET, headers=headers, handle_cloudflare=False)
        
        if resp and json_data: 
            csrf_token = json_data['csrfToken']
            if csrf_token:
                # Значение cookie
                self.website.csrf_token = csrf_token
                # logger.info(f'{self.website.user} получил CSRF токен: {self.website.csrf_token[:10]}...')
                return True
            else:
                print("CSRF token не найден")
                return False
        
        logger.error(f'{self.website.user} не удалось получить CSRF токен')
        return False
    
    async def sign_message(self, message_dict):
        """Подписывает сообщение с использованием приватного ключа"""
        try:
            # Создаем строковое представление сообщения в формате EIP-191
            message_str = (
                f"loyalty.campnetwork.xyz wants you to sign in with your Ethereum account:\n"
                f"{message_dict['address']}\n\n"
                f"{message_dict['statement']}\n\n"
                f"URI: {message_dict['uri']}\n"
                f"Version: {message_dict['version']}\n"
                f"Chain ID: {message_dict['chainId']}\n"
                f"Nonce: {message_dict['nonce']}\n"
                f"Issued At: {message_dict['issuedAt']}"
            )
            
            # Кодируем сообщение для подписи
            message_bytes = encode_defunct(text=message_str)
            
            # Подписываем сообщение
            sign = self.website.client.account.sign_message(message_bytes)
            signature = sign.signature.hex()
            
            # logger.info(f'{self.website.user} успешно подписал сообщение')
            return signature
            
        except Exception as e:
            logger.error(f'{self.website.user} ошибка при подписании сообщения: {str(e)}')
            raise Exception(f'Ошибка при подписании сообщения: {str(e)}')

    async def nonce(self):
        """Получает nonce для аутентификации"""
        headers = self.website.http.get_headers({
            'x-dyn-version': 'WalletKit/3.9.11',
            'x-dyn-api-version': 'API/0.0.586',
        })
        url = 'https://app.dynamicauth.com/api/v0/sdk/09a766ae-a662-4d96-904a-28d1c9e4b587/nonce'
        resp, json_data = await self.website.http.request(url=url, method=GET, headers=headers, handle_cloudflare=False)
        if resp and json_data:
            try:
                nonce = json_data['nonce']
                return nonce
            except Exception:
                return False
        else:
            return False
    
    async def _get_nonce_and_csrf(self):
        """Получает nonce и CSRF токен для авторизации"""
        nonce = await self.nonce()
        if not nonce:
            logger.error(f'{self.website.user} не удалось получить nonce')
            return False
            
        if not await self.get_csrf_token():
            logger.error(f'{self.website.user} не удалось получить CSRF токен')
            return False
            
        self.website.nonce_value = nonce
        return nonce
    
    async def authenticate_with_credentials(self):
        """Аутентификация с использованием учетных данных Ethereum"""
        if not self.website.csrf_token:
            logger.error(f'{self.website.user} попытка аутентификации без CSRF токена')
            return False
        
            
        url = 'https://loyalty.campnetwork.xyz/api/auth/callback/credentials'
        
        # Текущая дата и время в формате ISO
        current_time = datetime.datetime.utcnow().isoformat('T') + 'Z'
        
        # Создаем сообщение для подписи
        message = {
            "domain": "loyalty.campnetwork.xyz",
            "address": self.website.user.public_key,
            "statement": "Sign in to the app. Powered by Snag Solutions.",
            "uri": "https://loyalty.campnetwork.xyz",
            "version": "1",
            "chainId": 1,
            "nonce": self.website.nonce_value,
            "issuedAt": current_time
        }
        
        # Подписываем сообщение
        signature = await self.sign_message(message)
        
        form_data = {
            'message': json.dumps(message),
            'accessToken': signature,  # По анализу CURL-запросов, accessToken и signature одинаковы
            'signature': signature,
            'walletConnectorName': 'Rabby',
            'walletAddress': self.website.user.public_key,
            'redirect': 'false',
            'callbackUrl': '/protected',
            'chainType': 'evm',
            'csrfToken': self.website.csrf_token,
            'json': 'true'
        }
        
        headers = self.website.http.get_headers({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Origin': 'https://loyalty.campnetwork.xyz',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        # Включаем автоматическое решение Cloudflare Turnstile
        resp, json_data = await self.website.http.request(url=url, method=POST, data=form_data, headers=headers, handle_cloudflare=False)
        
        if resp:
            # Проверяем наличие токена сессии в куках
            if '__Secure-next-auth.session-token' in self.website.cookies:
                self.website.auth_session_token = self.website.cookies['__Secure-next-auth.session-token']
                # logger.info(f'{self.website.user} успешно аутентифицирован, получен токен сессии')
                return True
                
        logger.error(f'{self.website.user} не удалось аутентифицироваться')
        return False
    
    async def get_session(self):
        """Получение данных сессии"""
        if not self.website.auth_session_token:
            logger.error(f'{self.website.user} попытка получить сессию без токена')
            return False
            
        url = 'https://loyalty.campnetwork.xyz/api/auth/session'
        headers = self.website.http.get_headers({
            'Content-Type': 'application/json',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        # Включаем автоматическое решение Cloudflare Turnstile
        resp, json_data = await self.website.http.request(url=url, method=GET, headers=headers, handle_cloudflare=False)
        
        if resp and json_data:
            session_data = json_data
            if 'user' in session_data and 'id' in session_data['user']:
                self.website.session_data = session_data
                logger.info(f'{self.website.user} получил данные сессии, ID пользователя: {session_data["user"]["id"]}')
                return session_data
                
        logger.error(f'{self.website.user} не удалось получить данные сессии')
        return False
    
    async def save_session_to_db(self):
        """Сохраняет токен сессии и другие данные в базу данных"""
        try:
            if not self.website.auth_session_token or not self.website.session_data:
                logger.error(f'{self.website.user} попытка сохранить сессию без токена или данных')
                return False
            
            async with Session() as session:
                db = DB(session=session)
                result = await db.update_session(
                    id=self.website.user.id,
                    session_token=self.website.auth_session_token, 
                    session_id=self.website.session_data['user']['id'],
                    session_expires=self.website.session_data['expires']
                )
            
            if result:
                # logger.info(f'{self.website.user} данные сессии успешно сохранены в БД')
                return True
            else:
                logger.error(f'{self.website.user} не удалось сохранить данные сессии в БД')
                return False
            
        except Exception as e:
            logger.error(f'{self.website.user} ошибка при сохранении сессии в БД: {str(e)}')
            return False
    
    async def sign_out(self):
        """Выход из системы"""
        if not self.website.csrf_token:
            logger.error(f'{self.website.user} попытка выхода без CSRF токена')
            return False
            
        url = 'https://loyalty.campnetwork.xyz/api/auth/signout'
        form_data = {
            'csrfToken': self.website.csrf_token,
            'callbackUrl': 'https://loyalty.campnetwork.xyz/home',
            'json': 'true'
        }
        
        headers = self.website.http.get_headers({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Origin': 'https://loyalty.campnetwork.xyz',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        # Включаем автоматическое решение Cloudflare Turnstile
        resp, json_data = await self.website.http.request(url=url, method=POST, data=form_data, headers=headers, handle_cloudflare=False)
        
        if resp:
            # logger.info(f'{self.website.user} успешно вышел из системы')
            return True
                
        logger.error(f'{self.website.user} не удалось выйти из системы')
        return False


class WebSite:
    """Основной класс для взаимодействия с сайтом CampNetwork"""
    
    def __init__(self, user: User, session: ClientSession, client=None):
        self.user = user
        self.session = session
        self.client = client  # Клиент для работы с блокчейном
        self.cookies = {}
        self.csrf_token = None
        self.auth_session_token = None
        self.session_data = None
        self.nonce_value = None
        
        # Инициализация компонентов
        self.cloudflare = CloudflareHandler(self)
        self.http = HttpClient(self)
        self.auth = AuthManager(self)
        
    async def login(self):
        """Полный процесс авторизации с сохранением сессии в БД"""
        try:
            # Определяем последовательность шагов авторизации
            login_steps = [
                self.auth.test_resp,
                self.auth.connect_wallet,
                self.auth._get_nonce_and_csrf,
                self.auth.sign_out,  # Выход перед новой авторизацией
                self.auth.authenticate_with_credentials,
                self.auth.get_session,
                self.auth.save_session_to_db
            ]
            
            # Последовательно выполняем шаги, останавливаясь при первой ошибке
            for step in login_steps:
                step_name = step.__name__
                # logger.info(f'{self.user} выполняется шаг {step_name}')
                
                result = await step()
                if not result:
                    logger.error(f'{self.user} ошибка на шаге {step_name}')
                    return False
            
            logger.success(f'{self.user} успешно прошел полный процесс авторизации')
            return self.session_data
                
        except Exception as e:
            logger.error(f'{self.user} ошибка в процессе авторизации: {str(e)}')
            return False
