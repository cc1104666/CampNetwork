from .models import User
import random
import json
from sqlalchemy import select, update, text
from libs.eth_async.utils.utils import parse_proxy


class DB:
    def __init__(self, session):
        self.session = session

    async def add_wallet(self, private_key: str, public_key: str, user_agent: str, proxy: str | None = None, twitter_token: str | None = None):
        """将钱包添加到数据库"""
        wallet = User(
            private_key=private_key,
            public_key=public_key,
            proxy=proxy,
            user_agent=user_agent,
            twitter_token=twitter_token,
            proxy_status="OK",
            twitter_status="OK"
        )
        try:
            self.session.add(wallet)
            await self.session.flush()  # 检查添加时是否有错误
        except Exception as e:
            return False
        return True

    async def update_proxy(self, user_id: int, available_proxies: list):
        """更新用户的代理"""
        existing_proxies = await self.session.execute(select(User.proxy))
        existing_proxies = {proxy[0] for proxy in existing_proxies.all()}  # 转换为集合

        # 过滤列表，只保留唯一的代理
        unique_proxies = list(set(available_proxies) - existing_proxies)
        if not unique_proxies:
            raise ValueError("没有可用的唯一代理！")

        # 随机选择一个唯一代理
        new_proxy = random.choice(unique_proxies)
        new_proxy = parse_proxy(new_proxy)

        # 更新用户的代理
        user = await self.session.get(User, user_id)
        if user:
            user.proxy = new_proxy
            user.proxy_status = "OK"  # 更新时重置状态
            await self.session.commit()
            return new_proxy
        else:
            raise ValueError(f"未找到 ID 为 {user_id} 的用户")
    
    async def update_twitter_token(self, user_id: int, available_tokens: list):
        """更新用户的 Twitter 令牌"""
        existing_tokens = await self.session.execute(select(User.twitter_token))
        existing_tokens = {token[0] for token in existing_tokens.all() if token[0]}  # 转换为集合

        # 过滤列表，只保留唯一的令牌
        unique_tokens = list(set(available_tokens) - existing_tokens)
        if not unique_tokens:
            raise ValueError("没有可用的唯一 Twitter 令牌！")

        # 随机选择一个唯一令牌
        new_token = random.choice(unique_tokens)

        # 更新用户的令牌
        user = await self.session.get(User, user_id)
        if user:
            user.twitter_token = new_token
            user.twitter_status = "OK"  # 更新时重置状态
            await self.session.commit()
            return new_token
        else:
            raise ValueError(f"未找到 ID 为 {user_id} 的用户")

    async def get_all_wallets(self) -> list:
        """从数据库获取所有钱包"""
        result = await self.session.execute(select(User))  # 执行查询所有记录
        wallets = result.scalars().all()  # 返回表中的所有行作为列表
        return wallets

    async def mark_quest_completed(self, user_id: int, quest_id: str) -> bool:
        """
        将指定用户的任务标记为已完成
        
        Args:
            user_id: 用户 ID
            quest_id: 已完成任务的 ID
            
        Returns:
            成功状态
        """
        try:
            # 获取用户
            user = await self.session.get(User, user_id)
            if not user:
                return False
            
            # 获取当前已完成的任务
            completed_quests = user.completed_quests.split(',') if user.completed_quests else []
            
            # 如果任务不在列表中，则添加
            if quest_id not in completed_quests:
                completed_quests.append(quest_id)
            
            # 更新数据库中的字段
            user.completed_quests = ','.join(completed_quests)
            await self.session.commit()
            
            return True
            
        except Exception as e:
            return False

    async def is_quest_completed(self, user_id: int, quest_id: str) -> bool:
        """
        检查指定用户是否已完成任务
        
        Args:
            user_id: 用户 ID
            quest_id: 任务 ID
            
        Returns:
            完成状态
        """
        try:
            # 获取用户
            user = await self.session.get(User, user_id)
            if not user or not user.completed_quests:
                return False
            
            # 检查任务是否在已完成列表中
            completed_quests = user.completed_quests.split(',')
            return quest_id in completed_quests
            
        except Exception as e:
            return False

    async def get_completed_quests(self, user_id: int) -> list:
        """
        获取指定用户已完成的任务列表
        
        Args:
            user_id: 用户 ID
            
        Returns:
            已完成任务列表（ID）
        """
        try:
            # 获取用户
            user = await self.session.get(User, user_id)
            if not user or not user.completed_quests:
                return []
            
            # 返回已完成任务列表
            return user.completed_quests.split(',')
            
        except Exception as e:
            return []
            
    # --- 添加新的资源管理函数 ---
    
    async def mark_proxy_as_bad(self, user_id: int) -> bool:
        """
        将用户的代理标记为不良
        
        Args:
            user_id: 用户 ID
            
        Returns:
            成功状态
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False
                
            user.proxy_status = "BAD"
            await self.session.commit()
            return True
        except Exception as e:
            return False
    
    async def mark_twitter_as_bad(self, user_id: int) -> bool:
        """
        将用户的 Twitter 令牌标记为不良
        
        Args:
            user_id: 用户 ID
            
        Returns:
            成功状态
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False
                
            user.twitter_status = "BAD"
            await self.session.commit()
            return True
        except Exception as e:
            return False
    
    async def get_wallets_with_bad_proxy(self) -> list:
        """
        Получает список кошельков с плохими прокси
        
        Returns:
            Список кошельков
        """
        query = select(User).where(User.proxy_status == "BAD")
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_wallets_with_bad_twitter(self) -> list:
        """
        Получает список кошельков с плохими токенами Twitter
        
        Returns:
            Список кошельков
        """
        query = select(User).where(User.twitter_status == "BAD")
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_bad_resources_count(self) -> tuple:
        """
        Получает количество плохих ресурсов
        
        Returns:
            (bad_proxies, bad_twitter): Количество плохих ресурсов
        """
        bad_proxies_query = select(User).where(User.proxy_status == "BAD")
        bad_proxies_result = await self.session.execute(bad_proxies_query)
        bad_proxies = len(bad_proxies_result.scalars().all())
        
        bad_twitter_query = select(User).where(User.twitter_status == "BAD")
        bad_twitter_result = await self.session.execute(bad_twitter_query)
        bad_twitter = len(bad_twitter_result.scalars().all())
        
        return bad_proxies, bad_twitter
    
    async def replace_bad_proxy(self, user_id: int, new_proxy: str) -> bool:
        """
        Заменяет плохое прокси пользователя
        
        Args:
            user_id: ID пользователя
            new_proxy: Новое прокси
            
        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False
                
            user.proxy = parse_proxy(new_proxy)
            user.proxy_status = "OK"
            await self.session.commit()
            return True
        except Exception as e:
            return False
    
    async def replace_bad_twitter(self, user_id: int, new_token: str) -> bool:
        """
        Заменяет плохой токен Twitter пользователя
        
        Args:
            user_id: ID пользователя
            new_token: Новый токен Twitter
            
        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False
                
            user.twitter_token = new_token
            user.twitter_status = "OK"
            await self.session.commit()
            return True
        except Exception as e:
            return False

    async def update_ref_code(self, user_id: int, ref_code: str | None) -> bool:
        """
        Обновляет реферальный код пользователя
        
        Args:
            user_id: ID пользователя
            ref_code: Реферальный код
            
        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False
                
            if not ref_code:
                return False
            user.ref_code = ref_code
            await self.session.commit()
            return True
        except Exception as e:
            return False

    async def get_available_ref_codes(self) -> list:
        """
        Получает список доступных реферальных кодов из БД
        
        Returns:
            Список реферальных кодов
        """
        query = select(User.ref_code).where(User.ref_code != None)
        result = await self.session.execute(query)
        codes = [code[0] for code in result.all() if code[0]]
        return codes
