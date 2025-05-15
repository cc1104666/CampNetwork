from .models import User
import random
import json
from sqlalchemy import select, update, text
from libs.eth_async.utils.utils import parse_proxy


class DB:
    def __init__(self, session):
        self.session = session

    async def add_wallet(self, private_key: str, public_key: str, user_agent: str, proxy: str | None = None, twitter_token: str | None = None):
        """Добавляет кошелек в базу данных"""
        wallet = User(
            private_key=private_key,
            public_key=public_key,
            proxy=proxy,
            user_agent=user_agent,
            twitter_token=twitter_token
        )
        try:
            self.session.add(wallet)
            await self.session.flush()  # Проверяем наличие ошибок при добавлении
        except Exception as e:
            return False
        return True

    async def update_proxy(self, user_id: int, available_proxies: list):
        """Обновляет прокси для пользователя"""
        existing_proxies = await self.session.execute(select(User.proxy))
        existing_proxies = {proxy[0] for proxy in existing_proxies.all()}  # Преобразуем в множество

        # Фильтруем список, оставляя только уникальные прокси
        unique_proxies = list(set(available_proxies) - existing_proxies)
        if not unique_proxies:
            raise ValueError("Нет доступных уникальных прокси!")

        # Выбираем случайный уникальный прокси
        new_proxy = random.choice(unique_proxies)
        new_proxy = parse_proxy(new_proxy)

        # Обновляем прокси для пользователя
        user = await self.session.get(User, user_id)
        if user:
            user.proxy = new_proxy
            await self.session.commit()
            return new_proxy
        else:
            raise ValueError(f"Пользователь с id {user_id} не найден")

    async def get_all_wallets(self) -> list:
        """Получает все кошельки из базы данных"""
        result = await self.session.execute(select(User))  # выполняем запрос ко всем записям в таблице
        wallets = result.scalars().all()  # возвращаем все строки из таблицы как список
        return wallets

    async def mark_quest_completed(self, user_id: int, quest_id: str) -> bool:
        """
        Отмечает задание как выполненное для указанного пользователя
        
        Args:
            user_id: ID пользователя
            quest_id: ID выполненного задания
            
        Returns:
            Статус успеха
        """
        try:
            # Получаем пользователя
            user = await self.session.get(User, user_id)
            if not user:
                return False
            
            # Получаем текущие выполненные квесты
            completed_quests = user.completed_quests.split(',') if user.completed_quests else []
            
            # Добавляем задание, если его там нет
            if quest_id not in completed_quests:
                completed_quests.append(quest_id)
            
            # Обновляем поле в БД
            user.completed_quests = ','.join(completed_quests)
            await self.session.commit()
            
            return True
            
        except Exception as e:
            return False

    async def is_quest_completed(self, user_id: int, quest_id: str) -> bool:
        """
        Проверяет, выполнено ли задание указанным пользователем
        
        Args:
            user_id: ID пользователя
            quest_id: ID задания
            
        Returns:
            Статус выполнения
        """
        try:
            # Получаем пользователя
            user = await self.session.get(User, user_id)
            if not user or not user.completed_quests:
                return False
            
            # Проверяем, есть ли задание в списке выполненных
            completed_quests = user.completed_quests.split(',')
            return quest_id in completed_quests
            
        except Exception as e:
            return False

    async def get_completed_quests(self, user_id: int) -> list:
        """
        Получает список выполненных заданий для указанного пользователя
        
        Args:
            user_id: ID пользователя
            
        Returns:
            Список выполненных заданий (ID)
        """
        try:
            # Получаем пользователя
            user = await self.session.get(User, user_id)
            if not user or not user.completed_quests:
                return []
            
            # Возвращаем список выполненных заданий
            return user.completed_quests.split(',')
            
        except Exception as e:
            return []

