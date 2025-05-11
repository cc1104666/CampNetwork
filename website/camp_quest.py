import asyncio
import random
import json
from datetime import datetime
from typing import List, Dict, Optional, Union, Tuple
from loguru import logger
import aiohttp
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from utils.db_api_async.models import User


class CampQuestManager:
    """Менеджер для выполнения заданий в CampNetwork, использующий сохраненные данные сессии"""
    
    # ID заданий, собранные из curl-запросов
    QUEST_IDS = {
        "CampNetwork": "2585eb2f-7cac-45d1-88db-13608762bf17",
        "CampStory": "541ff274-95c5-409a-9ea2-c80ec2719d7e",
        "Cristal": "d4fdee29-c60f-40f2-8795-1da0e9e5414e",
        "Belgrano": "e6eda663-977e-4d71-a03c-a1020db88064",
        "SummitX": "211c9b79-ff65-42f8-a59a-ad0539129aa9",
        "Clusters": "3ea83621-0087-4fc1-9967-c21265e2c369",
        "PictoBot": "2ba6c29a-69a1-4ff8-ac61-f4b19431f8d2",
        "PictoCommunity": "2233dcaa-a2be-49fb-b322-28bf9d387475",
        "TokenTails": "06b0d411-c1df-4cc5-a72c-e47dc911a0b3",
        "Arcoin": "aa08b2a5-eaab-469c-9e6f-e3a380c23faa",
        "Pixudi": "9f8edb41-4867-48e0-8d7a-8437c2c6e1b1",
        "JukieBlox": "46a1b202-ab7b-4c29-bf13-417c6a8267af",
        "StoryChain": "4345ec66-0746-4a77-85d0-a79db42612b1",
        "ScorePlay": "e7c0f882-82b7-499e-8a05-40528e0047ee",
        "WideWorlds": "d0928019-b49f-4ffd-8450-d7f5d3821f59",
        "RewardedTv": "d7a3a18b-38fd-45d5-937a-f974dff403bd",
        "Kraft": "f4de4fa8-ad5c-45c9-a804-0483309de9f9",
    }
    
    # URL для запросов
    BASE_URL = "https://loyalty.campnetwork.xyz"
    COMPLETE_URL_TEMPLATE = f"{BASE_URL}/api/loyalty/rules/{{quest_id}}/complete"
    STATUS_URL = f"{BASE_URL}/api/loyalty/rules/status"
    SESSION_URL = f"{BASE_URL}/api/auth/session"

    def __init__(self, user: User, session: aiohttp.ClientSession):
        self.user = user
        self.session = session
        self.cookies = {}
        self.completed_quests = []
        self.quest_status = {}
        
        # Загружаем сохраненные cookies из БД
        if user.camp_session_token:
            self.cookies["__Secure-next-auth.session-token"] = user.camp_session_token
    
    async def get_headers(self, additional_headers=None):
        """Создает базовые заголовки для запросов"""
        base_headers = {
            'User-Agent': self.user.user_agent,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Referer': 'https://loyalty.campnetwork.xyz/loyalty',
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
    
    async def request(self, url: str, method: str, data=None, json_data=None, 
                     params=None, headers=None, timeout=30, retries=3) -> Tuple[bool, Union[Dict, str]]:
        """Выполняет HTTP-запрос с автоматическими повторными попытками при ошибках"""
        base_headers = await self.get_headers(headers)
        
        # Настраиваем запрос
        request_kwargs = {
            'url': url,
            'proxy': self.user.proxy,
            'headers': base_headers,
            'cookies': self.cookies,
            'timeout': aiohttp.ClientTimeout(total=timeout)
        }
        
        # Добавляем параметры если они указаны
        if json_data is not None:
            request_kwargs['json'] = json_data
        if data is not None:
            request_kwargs['data'] = data
        if params is not None:
            request_kwargs['params'] = params
        
        # Выполняем запрос с повторными попытками
        for attempt in range(retries):
            try:
                async with getattr(self.session, method.lower())(**request_kwargs) as resp:
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
                    
                    # Клиентские ошибки (4xx)
                    if 400 <= resp.status < 500:
                        logger.warning(f"{self.user} получен статус {resp.status} при запросе {url}")
                        response_text = await resp.text()
                        
                        # Проверяем, может быть проблема с сессией
                        if resp.status == 401 or resp.status == 403:
                            logger.error(f"{self.user} ошибка авторизации. Возможно, сессия истекла: {response_text}")
                            return False, "AUTH_ERROR"
                            
                        return False, response_text
                        
                    # Серверные ошибки (5xx)
                    elif 500 <= resp.status < 600:
                        logger.warning(f"{self.user} получен статус {resp.status}, повторная попытка {attempt+1}/{retries}")
                        await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                        continue
                    
                    return False, await resp.text()
                    
            except (aiohttp.ClientConnectionError, asyncio.TimeoutError) as e:
                logger.warning(f"{self.user} ошибка соединения при запросе {url}, попытка {attempt+1}/{retries}: {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Экспоненциальная задержка
                continue
            except Exception as e:
                logger.error(f"{self.user} неожиданная ошибка при запросе {url}: {str(e)}")
                return False, str(e)
                
        # Если все попытки исчерпаны
        logger.error(f"{self.user} исчерпаны все попытки запроса {url}")
        return False, "MAX_RETRIES_EXCEEDED"
        
    async def get_session_info(self) -> Dict:
        """Получает информацию о текущей сессии пользователя"""
        success, data = await self.request(url=self.SESSION_URL, method="GET")
        
        if success and isinstance(data, dict) and 'user' in data:
            return data
        else:
            logger.error(f"Не удалось получить данные сессии для {self.user}")
            return {}
    
    async def get_status_params(self) -> Dict:
        """Получает параметры для запроса статуса заданий"""
        # Пробуем использовать сохраненный в БД ID пользователя
        if self.user.camp_session_user_id:
            return {
                "userId": self.user.camp_session_user_id,
                "websiteId": "32afc5c9-f0fb-4938-9572-775dee0b4a2b",
                "organizationId": "26a1764f-5637-425e-89fa-2f3fb86e758c"
            }
        
        # Если ID не сохранен, получаем его из сессии
        session_data = await self.get_session_info()
        if session_data and 'user' in session_data and 'id' in session_data['user']:
            return {
                "userId": session_data['user']['id'],
                "websiteId": "32afc5c9-f0fb-4938-9572-775dee0b4a2b",
                "organizationId": "26a1764f-5637-425e-89fa-2f3fb86e758c"
            }
        
        return {}
    
    async def complete_quest(self, quest_name: str) -> bool:
        """Выполняет задание по его имени"""
        quest_id = self.QUEST_IDS.get(quest_name)
        if not quest_id:
            logger.error(f"Задание {quest_name} не найдено в списке")
            return False
        
        try:
            url = self.COMPLETE_URL_TEMPLATE.format(quest_id=quest_id)
            
            # Задержка для имитации человеческого поведения
            await asyncio.sleep(random.uniform(1.5, 4.0))
            
            logger.info(f"{self.user} выполняет задание {quest_name}")
            
            # Заголовки для запроса выполнения задания
            headers = {
                'Content-Type': 'application/json',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Priority': 'u=0',
            }
            
            success, response = await self.request(
                url=url,
                method="POST",
                json_data={},
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} успешно выполнил задание {quest_name}")
                self.completed_quests.append(quest_name)
                return True
            elif response == "AUTH_ERROR":
                logger.error(f"{self.user} ошибка авторизации при выполнении задания {quest_name}")
                return False
            else:
                logger.error(f"{self.user} ошибка при выполнении задания {quest_name}: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} исключение при выполнении задания {quest_name}: {e}")
            return False
    
    async def check_quests_status(self) -> Dict:
        """Проверяет статус всех заданий"""
        params = await self.get_status_params()
        
        if not params:
            logger.error(f"{self.user} не удалось получить параметры для запроса статуса")
            return {}
        
        success, response = await self.request(
            url=self.STATUS_URL,
            method="GET",
            params=params
        )
        
        if success and isinstance(response, dict):
            # Обновляем статус заданий
            self.quest_status = response
            logger.info(f"{self.user} получен статус заданий (всего {len(response.get('rules', []))})")
            return response
        elif response == "AUTH_ERROR":
            logger.error(f"{self.user} ошибка авторизации при получении статуса заданий")
            return {}
        else:
            logger.error(f"{self.user} ошибка при получении статуса заданий: {response}")
            return {}
    
    async def get_incomplete_quests(self) -> List[str]:
        """Получает список незавершенных заданий"""
        status = await self.check_quests_status()
        
        if not status or 'rules' not in status:
            # Если не удалось получить статус, возвращаем все задания
            logger.warning(f"{self.user} не удалось получить статус, возвращаю все задания")
            return list(self.QUEST_IDS.keys())
        
        incomplete = []
        
        # Получаем ID всех незавершенных заданий из статуса
        completed_quest_ids = {rule['id'] for rule in status['rules'] if rule.get('userCompleted')}
        
        # Формируем список незавершенных заданий
        for quest_name, quest_id in self.QUEST_IDS.items():
            if quest_id not in completed_quest_ids:
                incomplete.append(quest_name)
        
        logger.info(f"{self.user} незавершенные задания ({len(incomplete)}): {', '.join(incomplete) if incomplete else 'нет'}")
        return incomplete
    
    async def complete_all_quests(self, retry_failed: bool = True, max_retries: int = 3) -> Dict[str, bool]:
        """Выполняет все незавершенные задания"""
        results = {}
        
        # Получаем список незавершенных заданий
        incomplete_quests = await self.get_incomplete_quests()
        
        if not incomplete_quests:
            logger.info(f"{self.user} все задания уже выполнены")
            return results
        
        # Словарь для отслеживания попыток
        retry_counts = {quest: 0 for quest in incomplete_quests}
        
        # Выполняем задания
        for quest_name in incomplete_quests:
            success = await self.complete_quest(quest_name)
            results[quest_name] = success
            
            # Делаем задержку между заданиями
            await asyncio.sleep(random.uniform(2.0, 5.0))
        
        # Проверяем результаты и повторяем неудачные задания если нужно
        if retry_failed:
            # Получаем обновленный список незавершенных заданий
            remaining = await self.get_incomplete_quests()
            
            # Повторяем неудачные задания
            for quest_name in remaining:
                # Учитываем только задания из первоначального списка
                if quest_name in retry_counts:
                    retry_counts[quest_name] += 1
                    
                    if retry_counts[quest_name] <= max_retries:
                        logger.warning(f"{self.user} повторная попытка {retry_counts[quest_name]}/{max_retries} для задания {quest_name}")
                        
                        # Делаем увеличенную задержку перед повторной попыткой
                        await asyncio.sleep(random.uniform(3.0, 7.0))
                        
                        success = await self.complete_quest(quest_name)
                        results[quest_name] = success
        
        # Получаем итоговую статистику
        completed = sum(1 for result in results.values() if result)
        logger.success(f"{self.user} выполнено {completed} из {len(results)} заданий")
        
        return results
    
    async def complete_specific_quests(self, quest_names: List[str]) -> Dict[str, bool]:
        """Выполняет только указанные задания"""
        results = {}
        
        # Проверяем, что все указанные задания существуют
        invalid_quests = [name for name in quest_names if name not in self.QUEST_IDS]
        if invalid_quests:
            logger.warning(f"{self.user} следующие задания не найдены: {', '.join(invalid_quests)}")
        
        # Фильтруем только существующие задания
        valid_quests = [name for name in quest_names if name in self.QUEST_IDS]
        
        if not valid_quests:
            logger.error(f"{self.user} нет действительных заданий для выполнения")
            return results
        
        # Проверяем статус для определения уже выполненных заданий
        status = await self.check_quests_status()
        
        if status and 'rules' in status:
            # Получаем ID всех выполненных заданий
            completed_quest_ids = {rule['id'] for rule in status['rules'] if rule.get('userCompleted')}
            
            # Фильтруем только незавершенные задания
            valid_quests = [
                name for name in valid_quests 
                if self.QUEST_IDS[name] not in completed_quest_ids
            ]
            
            if not valid_quests:
                logger.info(f"{self.user} все указанные задания уже выполнены")
                return results
        
        # Выполняем задания
        for quest_name in valid_quests:
            success = await self.complete_quest(quest_name)
            results[quest_name] = success
            
            # Делаем задержку между заданиями
            await asyncio.sleep(random.uniform(2.0, 5.0))
        
        return results
    
    async def get_stats(self) -> Dict:
        """Получает статистику выполнения заданий и баллов"""
        status = await self.check_quests_status()
        
        if not status or 'rules' not in status:
            return {
                "completed_count": 0,
                "total_count": len(self.QUEST_IDS),
                "total_points": 0
            }
        
        completed_count = sum(1 for rule in status['rules'] if rule.get('userCompleted'))
        
        return {
            "completed_count": completed_count,
            "total_count": len(status['rules']),
            "total_points": status.get('totalPoints', 0)
        }
