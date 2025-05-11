import asyncio
import random
from typing import Dict, List, Optional, Any
from loguru import logger
from website.http_client import BaseHttpClient


class QuestClient(BaseHttpClient):
    """Клиент для взаимодействия с заданиями CampNetwork"""
    
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.completed_quests = []  # Список выполненных заданий
        self.quest_status = {}  # Статус всех заданий
        self.user_id = kwargs.get('user_id')  # ID пользователя
    
    def set_user_id(self, user_id: str) -> None:
        """
        Устанавливает ID пользователя
        
        Args:
            user_id: ID пользователя
        """
        self.user_id = user_id
    
    async def get_status_params(self) -> Dict[str, str]:
        """
        Получает параметры для запроса статуса заданий
        
        Returns:
            Параметры для запроса статуса
        """
        if not self.user_id:
            logger.error(f"{self.user} попытка получить параметры статуса без ID пользователя")
            return {}
            
        return {
            "userId": self.user_id,
            "websiteId": "32afc5c9-f0fb-4938-9572-775dee0b4a2b",
            "organizationId": "26a1764f-5637-425e-89fa-2f3fb86e758c"
        }
    
    async def check_quests_status(self) -> Dict:
        """
        Проверяет статус всех заданий
        
        Returns:
            Статус заданий
        """
        params = await self.get_status_params()
        if not params:
            return {}
            
        success, response = await self.request(
            url=self.STATUS_URL,
            method="GET",
            params=params
        )
        
        if success and isinstance(response, dict):
            self.quest_status = response
            logger.info(f"{self.user} получен статус заданий (всего {len(response.get('rules', []))})")
            return response
        else:
            logger.error(f"{self.user} не удалось получить статус заданий: {response}")
            return {}
    
    async def get_incomplete_quests(self) -> List[str]:
        """
        Получает список незавершенных заданий
        
        Returns:
            Список незавершенных заданий
        """
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
    
    async def complete_quest(self, quest_name: str) -> bool:
        """
        Выполняет задание по его имени
        
        Args:
            quest_name: Название задания
            
        Returns:
            Статус успеха
        """
        quest_id = self.QUEST_IDS.get(quest_name)
        if not quest_id:
            logger.error(f"Задание {quest_name} не найдено в списке")
            return False
        
        try:
            url = self.COMPLETE_URL_TEMPLATE.format(quest_id=quest_id)
            
            # Добавляем случайную задержку для имитации человеческого поведения
            await asyncio.sleep(random.uniform(1.5, 4.0))
            
            logger.info(f"{self.user} выполняет задание {quest_name}")
            
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Priority': 'u=0',
            })
            
            success, response = await self.request(
                url=url,
                method="POST",
                json_data={},  # Пустой JSON как в curl-запросах
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} успешно выполнил задание {quest_name}")
                self.completed_quests.append(quest_name)
                return True
            else:
                logger.error(f"{self.user} ошибка при выполнении задания {quest_name}: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} исключение при выполнении задания {quest_name}: {e}")
            return False
    
    async def complete_all_quests(self, retry_failed: bool = True, max_retries: int = 3) -> Dict[str, bool]:
        """
        Выполняет все незавершенные задания
        
        Args:
            retry_failed: Повторять ли неудачные задания
            max_retries: Максимальное количество повторных попыток
            
        Returns:
            Результаты выполнения заданий
        """
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
        """
        Выполняет только указанные задания
        
        Args:
            quest_names: Список названий заданий
            
        Returns:
            Результаты выполнения заданий
        """
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
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получает статистику выполнения заданий и баллов
        
        Returns:
            Статистика заданий
        """
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
