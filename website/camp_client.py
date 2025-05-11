from typing import Dict, List, Optional, Any
from loguru import logger
from utils.db_api_async.models import User
from libs.eth_async.client import Client
from libs.eth_async.data.models import Networks
from .auth_client import AuthClient
from .quest_client import QuestClient


class CampNetworkClient:
    """Основной клиент для CampNetwork, объединяющий авторизацию и работу с заданиями"""
    
    def __init__(self, user: User, client: Optional[Client] = None):
        """
        Инициализация клиента CampNetwork
        
        Args:
            user: Объект пользователя
            client: Клиент блокчейна (опционально)
        """
        self.user = user
        
        # Создаем клиенты для авторизации и работы с заданиями
        self.auth_client = AuthClient(user=user)
        self.quest_client = QuestClient(user=user)
        
        # ID заданий для удобного доступа
        self.QUEST_IDS = self.quest_client.QUEST_IDS
    
    async def login(self) -> bool:
        """
        Выполняет авторизацию на сайте
        
        Returns:
            Статус успеха
        """
        # Выполняем полный процесс авторизации
        success = await self.auth_client.login()
        
        if success:
            # Если авторизация успешна, передаем куки и ID пользователя клиенту заданий
            self.quest_client.cookies = self.auth_client.cookies
            self.quest_client.set_user_id(self.auth_client.user_id)
            return True
        else:
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
        # Проверяем, авторизованы ли мы
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} не авторизован, выполняю авторизацию")
            if not await self.login():
                logger.error(f"{self.user} не удалось авторизоваться, выполнение заданий невозможно")
                return {}
        
        # Выполняем все задания
        return await self.quest_client.complete_all_quests(
            retry_failed=retry_failed, 
            max_retries=max_retries
        )
    
    async def complete_specific_quests(self, quest_names: List[str]) -> Dict[str, bool]:
        """
        Выполняет только указанные задания
        
        Args:
            quest_names: Список названий заданий
            
        Returns:
            Результаты выполнения заданий
        """
        # Проверяем, авторизованы ли мы
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} не авторизован, выполняю авторизацию")
            if not await self.login():
                logger.error(f"{self.user} не удалось авторизоваться, выполнение заданий невозможно")
                return {}
        
        # Выполняем указанные задания
        return await self.quest_client.complete_specific_quests(quest_names)
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получает статистику выполнения заданий и баллов
        
        Returns:
            Статистика заданий
        """
        # Проверяем, авторизованы ли мы
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} не авторизован, выполняю авторизацию")
            if not await self.login():
                logger.error(f"{self.user} не удалось авторизоваться, получение статистики невозможно")
                return {"error": "Не удалось авторизоваться"}
        
        # Получаем статистику
        return await self.quest_client.get_stats()
