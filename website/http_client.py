import asyncio
import random
import json
import aiohttp
from typing import Dict, Tuple, Union, Optional
from loguru import logger
from utils.db_api_async.models import User


class BaseHttpClient:
    """Базовый HTTP-клиент для выполнения запросов"""
    
    def __init__(self, user: User):
        """
        Инициализация базового HTTP-клиента
        
        Args:
            user: Пользователь с приватным ключом и прокси
        """
        self.user = user
        self.cookies = {}
    
    async def get_headers(self, additional_headers: Optional[Dict] = None) -> Dict:
        """
        Создает базовые заголовки для запросов
        
        Args:
            additional_headers: Дополнительные заголовки
            
        Returns:
            Сформированные заголовки
        """
        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://loyalty.campnetwork.xyz/',
            'DNT': '1',
            'Sec-GPC': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Priority': 'u=4',
        }
        
        if additional_headers:
            base_headers.update(additional_headers)
            
        return base_headers

    async def request(
        self, 
        url: str, 
        method: str, 
        data: Optional[Dict] = None, 
        json_data: Optional[Dict] = None, 
        params: Optional[Dict] = None, 
        headers: Optional[Dict] = None, 
        timeout: int = 30, 
        retries: int = 3
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Выполняет HTTP-запрос с автоматическими повторными попытками
        
        Args:
            url: URL для запроса
            method: Метод запроса (GET, POST, etc.)
            data: Данные формы
            json_data: JSON данные
            params: Параметры URL
            headers: Дополнительные заголовки
            timeout: Таймаут запроса в секундах
            retries: Количество повторных попыток
            
        Returns:
            (bool, data): Статус успеха и данные ответа
        """
        base_headers = await self.get_headers(headers)
        
        # Настраиваем параметры запроса
        request_kwargs = {
            'url': url,
            'proxy': self.user.proxy,
            'headers': base_headers,
            'cookies': self.cookies,
            'timeout': timeout
        }
        
        # Добавляем опциональные параметры
        if json_data is not None:
            request_kwargs['json'] = json_data
        if data is not None:
            request_kwargs['data'] = data
        if params is not None:
            request_kwargs['params'] = params
        
        # Выполняем запрос с повторными попытками
        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with getattr(session, method.lower())(**request_kwargs) as resp:
                        # Сохраняем cookies из ответа
                        if resp.cookies:
                            for name, cookie in resp.cookies.items():
                                self.cookies[name] = cookie.value
                        
                        # Успешный ответ
                        if resp.status == 200 or resp.status == 202:
                            try:
                                json_resp = await resp.json()
                                return True, json_resp
                            except Exception:
                                return True, await resp.text()
                        
                        # Обработка ошибок
                        if 400 <= resp.status < 500:
                            logger.warning(f"{self.user} получен статус {resp.status} при запросе {url}")
                            response_text = await resp.text()
                            
                            # Проверяем, может быть проблема с авторизацией
                            if resp.status == 401 or resp.status == 403:
                                if "!DOCTYPE" not in response_text:
                                    logger.error(f"{self.user} ошибка авторизации: {response_text}")
                                return False, response_text
                            
                            # Проверяем на ограничение запросов
                            if resp.status == 429:
                                logger.warning(f"{self.user} превышен лимит запросов (429)")
                                
                                # Если это не последняя попытка, делаем большую задержку и пробуем снова
                                if attempt < retries - 1:
                                    wait_time = random.uniform(60, 120)  # 1-2 минуты
                                    logger.info(f"{self.user} ожидание {int(wait_time)} секунд перед следующей попыткой")
                                    await asyncio.sleep(wait_time)
                                    continue
                                
                                # Парсим ответ, чтобы получить возможный JSON с сообщением об ошибке
                                try:
                                    error_json = json.loads(response_text)
                                    return False, error_json
                                except:
                                    return False, "RATE_LIMIT"
                                    
                            # Парсим ответ, чтобы получить возможный JSON с сообщением об ошибке
                            try:
                                error_json = json.loads(response_text)
                                return False, error_json
                            except:
                                return False, response_text
                                
                        elif 500 <= resp.status < 600:
                            logger.warning(f"{self.user} получен статус {resp.status}, повторная попытка {attempt+1}/{retries}")
                            await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                            continue
                        
                        return False, await resp.text()
                        
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                logger.warning(f"{self.user} ошибка соединения при запросе {url}: {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                continue
            except Exception as e:
                logger.error(f"{self.user} неожиданная ошибка при запросе {url}: {str(e)}")
                return False, str(e)
                
        # Если все попытки исчерпаны
        logger.error(f"{self.user} исчерпаны все попытки запроса {url}")
        return False, "MAX_RETRIES_EXCEEDED"
