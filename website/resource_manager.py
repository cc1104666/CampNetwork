import os
from typing import List, Tuple, Optional
from loguru import logger
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config

class ResourceManager:
    """Класс для управления ресурсами (прокси, токены Twitter)"""
    
    def __init__(self):
        """Инициализация менеджера ресурсов"""
        # Кэш для отслеживания использованных ресурсов
        self.used_reserve_proxies = set()
        self.used_reserve_twitter = set()
    
    def _load_from_file(self, file_path: str) -> List[str]:
        """
        Загружает данные из файла
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            Список строк из файла
        """
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'r') as file:
                return [line.strip() for line in file if line.strip()]
        return []
    
    def _get_available_proxy(self) -> Optional[str]:
        """
        Получает доступное резервное прокси
        
        Returns:
            Прокси или None, если нет доступных
        """
        all_proxies = self._load_from_file(config.RESERVE_PROXY_FILE)
        available = [p for p in all_proxies if p not in self.used_reserve_proxies]
        
        if not available:
            return None
            
        proxy = available[0]  # Берем первое доступное
        self.used_reserve_proxies.add(proxy)
        return proxy
    
    def _get_available_twitter(self) -> Optional[str]:
        """
        Получает доступный резервный токен Twitter
        
        Returns:
            Токен или None, если нет доступных
        """
        all_tokens = self._load_from_file(config.RESERVE_TWITTER_FILE)
        available = [t for t in all_tokens if t not in self.used_reserve_twitter]
        
        if not available:
            return None
            
        token = available[0]  # Берем первый доступный
        self.used_reserve_twitter.add(token)
        return token
    
    async def get_bad_resources_stats(self) -> Tuple[int, int]:
        """
        Получает статистику плохих ресурсов
        
        Returns:
            (bad_proxies, bad_twitter): Количество плохих ресурсов
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_bad_resources_count()
    
    async def replace_proxy(self, user_id: int) -> Tuple[bool, str]:
        """
        Заменяет прокси пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            (success, message): Статус успеха и сообщение
        """
        new_proxy = self._get_available_proxy()
        if not new_proxy:
            return False, "Нет доступных резервных прокси"
        
        async with Session() as session:
            db = DB(session)
            success = await db.replace_bad_proxy(user_id, new_proxy)
            
            if success:
                return True, f"Прокси успешно заменено на {new_proxy}"
            else:
                return False, "Не удалось заменить прокси"
    
    async def replace_twitter(self, user_id: int) -> Tuple[bool, str]:
        """
        Заменяет токен Twitter пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            (success, message): Статус успеха и сообщение
        """
        new_token = self._get_available_twitter()
        if not new_token:
            return False, "Нет доступных резервных токенов Twitter"
        
        async with Session() as session:
            db = DB(session)
            success = await db.replace_bad_twitter(user_id, new_token)
            
            if success:
                return True, "Токен Twitter успешно заменен"
            else:
                return False, "Не удалось заменить токен Twitter"
    
    async def mark_proxy_as_bad(self, user_id: int) -> bool:
        """
        Отмечает прокси пользователя как плохое
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Статус успеха
        """
        async with Session() as session:
            db = DB(session)
            return await db.mark_proxy_as_bad(user_id)
    
    async def mark_twitter_as_bad(self, user_id: int) -> bool:
        """
        Отмечает токен Twitter пользователя как плохой
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Статус успеха
        """
        async with Session() as session:
            db = DB(session)
            return await db.mark_twitter_as_bad(user_id)
    
    async def get_bad_proxies(self) -> List:
        """
        Получает список кошельков с плохими прокси
        
        Returns:
            Список кошельков
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_wallets_with_bad_proxy()
    
    async def get_bad_twitter(self) -> List:
        """
        Получает список кошельков с плохими токенами Twitter
        
        Returns:
            Список кошельков
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_wallets_with_bad_twitter()
    
    async def replace_all_bad_proxies(self) -> Tuple[int, int]:
        """
        Заменяет все плохие прокси
        
        Returns:
            (replaced, total): Количество замененных прокси и общее количество плохих прокси
        """
        replaced = 0
        
        async with Session() as session:
            db = DB(session)
            bad_proxies = await db.get_wallets_with_bad_proxy()
            
            for wallet in bad_proxies:
                success, _ = await self.replace_proxy(wallet.id)
                if success:
                    replaced += 1
            
            return replaced, len(bad_proxies)
    
    async def replace_all_bad_twitter(self) -> Tuple[int, int]:
        """
        Заменяет все плохие токены Twitter
        
        Returns:
            (replaced, total): Количество замененных токенов и общее количество плохих токенов
        """
        replaced = 0
        
        async with Session() as session:
            db = DB(session)
            bad_twitter = await db.get_wallets_with_bad_twitter()
            
            for wallet in bad_twitter:
                success, _ = await self.replace_twitter(wallet.id)
                if success:
                    replaced += 1
            
            return replaced, len(bad_twitter)
