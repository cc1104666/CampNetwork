from typing import Dict, List, Optional, Any
from loguru import logger
from utils.db_api_async.models import User
from libs.eth_async.client import Client
from libs.eth_async.data.models import Networks
from website.referral_manager import load_ref_codes, get_referral_code_for_registration
from data.models import Settings
from .auth_client import AuthClient
from .quest_client import QuestClient


class CampNetworkClient:
    """CampNetwork 主客户端，整合认证和任务功能"""
    
    def __init__(self, user: User, client: Optional[Client] = None):
        """
        初始化 CampNetwork 客户端
        
        Args:
            user: 用户对象
            client: 区块链客户端（可选）
        """
        self.user = user
        
        # 创建认证和任务客户端
        self.auth_client = AuthClient(user=user)
        self.quest_client = QuestClient(user=user)
        
        # 任务 ID 方便访问
        self.QUEST_IDS = self.quest_client.QUEST_IDS
    
    async def login(self, use_referral: bool = True) -> bool:
        """
        在网站上执行认证，必要时使用推荐码
        
        Args:
            use_referral: 认证时是否使用推荐码
            
        Returns:
            成功状态
        """
        referral_code = None
        
        # 获取推荐码设置
        settings = Settings()
        use_random_from_db, use_only_file_codes = settings.get_referral_settings()
        
        # 如果需要使用推荐码
        if use_referral and not self.user.completed_quests:
            # 如果指定只使用文件中的码
            if use_only_file_codes:
                file_codes = load_ref_codes()
                referral_code = file_codes[0] if file_codes else None
            else:
                # 使用标准码选择逻辑
                referral_code = await get_referral_code_for_registration(use_random_from_db=use_random_from_db)
        
        # 使用推荐码执行认证
        success = await self.auth_client.login_with_referral(referral_code=referral_code)
        
        if success:
            # 如果认证成功，将 cookies 和用户 ID 传递给任务客户端
            self.quest_client.cookies = self.auth_client.cookies
            self.quest_client.set_user_id(self.auth_client.user_id)
            return True
        else:
            return False

    async def complete_all_quests(self, retry_failed: bool = True, max_retries: int = 3) -> Dict[str, bool]:
        """
        执行所有未完成任务，处理错误
        
        Args:
            retry_failed: 是否重试失败的任务
            max_retries: 最大重试次数
            
        Returns:
            任务执行结果
        """
        # 检查是否已认证
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} 未认证，正在执行认证")
            auth_result = await self.login()
            
            if not auth_result:
                # 如果收到请求限制错误
                if isinstance(auth_result, str) and auth_result == "RATE_LIMIT":
                    logger.warning(f"{self.user} 由于请求限制，账户已进入等待状态")
                    return {"status": "RATE_LIMITED"}
                
                logger.error(f"{self.user} 无法认证，无法执行任务")
                return {}
        
        # 执行所有任务
        return await self.quest_client.complete_all_quests(
            retry_failed=retry_failed, 
            max_retries=max_retries
        )

    async def complete_specific_quests(self, quest_names: List[str]) -> Dict[str, bool]:
        """
        仅执行指定的任务，处理错误
        
        Args:
            quest_names: 任务名称列表
            
        Returns:
            任务执行结果
        """
        # 检查是否已认证
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} 未认证，正在执行认证")
            auth_result = await self.login()
            
            if not auth_result:
                # 如果收到请求限制错误
                if isinstance(auth_result, str) and auth_result == "RATE_LIMIT":
                    logger.warning(f"{self.user} 由于请求限制，账户已进入等待状态")
                    return {"status": "RATE_LIMITED"}
                
                logger.error(f"{self.user} 无法认证，无法执行任务")
                return {}
        
        # 执行指定任务
        return await self.quest_client.complete_specific_quests(quest_names)
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取任务完成和积分统计
        
        Returns:
            任务统计信息
        """
        # 检查是否已认证
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} 未认证，正在执行认证")
            if not await self.login():
                logger.error(f"{self.user} 无法认证，无法获取统计信息")
                return {"error": "无法认证"}
        
        # 获取统计信息
        return await self.quest_client.get_stats()
