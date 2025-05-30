import os
import random
from typing import List, Tuple, Optional
from loguru import logger
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config

class ResourceManager:
    """资源管理类（代理、Twitter 令牌）"""
    
    def __init__(self):
        """初始化资源管理器"""
        pass
    
    def _load_from_file(self, file_path: str) -> List[str]:
        """
        从文件加载数据
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件中的字符串列表
        """
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, 'r') as file:
                return [line.strip() for line in file if line.strip()]
        return []
    
    def _save_to_file(self, file_path: str, data: List[str]) -> bool:
        """
        保存数据到文件
        
        Args:
            file_path: 文件路径
            data: 要保存的字符串列表
            
        Returns:
            成功状态
        """
        try:
            with open(file_path, 'w') as file:
                for line in data:
                    file.write(f"{line}\n")
            return True
        except Exception as e:
            logger.error(f"保存到文件 {file_path} 时出错: {str(e)}")
            return False
    
    def _get_available_proxy(self) -> Optional[str]:
        """
        获取可用的备用代理并从文件中删除
        
        Returns:
            代理或 None（如果没有可用的）
        """
        # 从文件加载代理列表
        all_proxies = self._load_from_file(config.RESERVE_PROXY_FILE)
        
        if not all_proxies:
            logger.warning("文件中没有可用的代理")
            return None
        
        # 随机选择一个代理
        proxy = random.choice(all_proxies)
        
        # 从列表中删除选中的代理
        all_proxies.remove(proxy)
        
        # 将更新后的列表保存回文件
        if self._save_to_file(config.RESERVE_PROXY_FILE, all_proxies):
            logger.info(f"代理已成功选择并从文件中删除。剩余: {len(all_proxies)}")
        else:
            logger.warning(f"无法更新代理文件，但代理已被选择")
        
        return proxy
    
    def _get_available_twitter(self) -> Optional[str]:
        """
        获取可用的备用 Twitter 令牌并从文件中删除
        
        Returns:
            令牌或 None（如果没有可用的）
        """
        # 从文件加载令牌列表
        all_tokens = self._load_from_file(config.RESERVE_TWITTER_FILE)
        
        if not all_tokens:
            logger.warning("文件中没有可用的 Twitter 令牌")
            return None
        
        # 随机选择一个令牌
        token = random.choice(all_tokens)
        
        # 从列表中删除选中的令牌
        all_tokens.remove(token)
        
        # 将更新后的列表保存回文件
        if self._save_to_file(config.RESERVE_TWITTER_FILE, all_tokens):
            logger.info(f"Twitter 令牌已成功选择并从文件中删除。剩余: {len(all_tokens)}")
        else:
            logger.warning(f"无法更新 Twitter 令牌文件，但令牌已被选择")
        
        return token
    
    async def get_bad_resources_stats(self) -> Tuple[int, int]:
        """
        获取不良资源统计
        
        Returns:
            (bad_proxies, bad_twitter): 不良资源数量
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_bad_resources_count()
    
    async def replace_proxy(self, user_id: int) -> Tuple[bool, str]:
        """
        替换用户的代理
        
        Args:
            user_id: 用户 ID
            
        Returns:
            (success, message): 成功状态和消息
        """
        new_proxy = self._get_available_proxy()
        if not new_proxy:
            return False, "没有可用的备用代理"
        
        async with Session() as session:
            db = DB(session)
            success = await db.replace_bad_proxy(user_id, new_proxy)
            
            if success:
                return True, f"代理已成功替换为 {new_proxy}"
            else:
                # 不将代理返回文件，因为它可能已被使用
                return False, "无法替换代理"
    
    async def replace_twitter(self, user_id: int) -> Tuple[bool, str]:
        """
        替换用户的 Twitter 令牌
        
        Args:
            user_id: 用户 ID
            
        Returns:
            (success, message): 成功状态和消息
        """
        new_token = self._get_available_twitter()
        if not new_token:
            return False, "没有可用的备用 Twitter 令牌"
        
        async with Session() as session:
            db = DB(session)
            success = await db.replace_bad_twitter(user_id, new_token)
            
            if success:
                logger.success(f"Twitter 令牌已成功在数据库中为用户 {user_id} 替换")
                return True, "Twitter 令牌已成功替换"
            else:
                # 不将令牌返回文件，因为它可能已被使用
                logger.error(f"无法在数据库中为用户 {user_id} 替换 Twitter 令牌")
                return False, "无法替换 Twitter 令牌"
    
    async def mark_proxy_as_bad(self, user_id: int) -> bool:
        """
        将用户的代理标记为不良
        
        Args:
            user_id: 用户 ID
            
        Returns:
            成功状态
        """
        async with Session() as session:
            db = DB(session)
            return await db.mark_proxy_as_bad(user_id)
    
    async def mark_twitter_as_bad(self, user_id: int) -> bool:
        """
        将用户的 Twitter 令牌标记为不良
        
        Args:
            user_id: 用户 ID
            
        Returns:
            成功状态
        """
        async with Session() as session:
            db = DB(session)
            return await db.mark_twitter_as_bad(user_id)
    
    async def get_bad_proxies(self) -> List:
        """
        获取具有不良代理的钱包列表
        
        Returns:
            钱包列表
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_wallets_with_bad_proxy()
    
    async def get_bad_twitter(self) -> List:
        """
        获取具有不良 Twitter 令牌的钱包列表
        
        Returns:
            钱包列表
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_wallets_with_bad_twitter()
    
    async def replace_all_bad_proxies(self) -> Tuple[int, int]:
        """
        替换所有不良代理
        
        Returns:
            (replaced, total): 已替换的代理数量和不良代理总数
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
        替换所有不良 Twitter 令牌
        
        Returns:
            (replaced, total): 已替换的令牌数量和不良令牌总数
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
