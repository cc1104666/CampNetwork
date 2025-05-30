import asyncio
import random
import json
from typing import Dict, List, Optional, Any
from loguru import logger
from website.http_client import BaseHttpClient
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB


class QuestClient(BaseHttpClient):
    """CampNetwork 任务交互客户端"""
    
    # 从 curl 请求中收集的任务 ID
    QUEST_IDS = {
        "CampNetwork": "2585eb2f-7cac-45d1-88db-13608762bf17",
        "CampStory": "541ff274-95c5-409a-9ea2-c80ec2719d7e",
        "Bleetz": "10668db1-081d-40e2-9f42-06fafc67e4aa",
        "Cristal": "d4fdee29-c60f-40f2-8795-1da0e9e5414e",
        "Belgrano": "e6eda663-977e-4d71-a03c-a1020db88064",
        "SummitX": "211c9b79-ff65-42f8-a59a-ad0539129aa9",
        "Clusters": "3ea83621-0087-4fc1-9967-c21265e2c369",
        "PictoBot": "2ba6c29a-69a1-4ff8-ac61-f4b19431f8d2",
        "PanenkaTG": "be50eaa0-945a-4664-8d07-a2f02167cf38",
        "PictoCommunity": "2233dcaa-a2be-49fb-b322-28bf9d387475",
        "TokenTails": "06b0d411-c1df-4cc5-a72c-e47dc911a0b3",
        "AwanaTG": "9b87193e-c568-4a72-915d-1bdba060b00e",
        "Arcoin": "aa08b2a5-eaab-469c-9e6f-e3a380c23faa",
        "Pixudi": "9f8edb41-4867-48e0-8d7a-8437c2c6e1b1",
        "JukieBlox": "46a1b202-ab7b-4c29-bf13-417c6a8267af",
        "StoryChain": "4345ec66-0746-4a77-85d0-a79db42612b1",
        "ScorePlay": "e7c0f882-82b7-499e-8a05-40528e0047ee",
        "WideWorlds": "d0928019-b49f-4ffd-8450-d7f5d3821f59",
        "RewardedTv": "d7a3a18b-38fd-45d5-937a-f974dff403bd",
        "Kraft": "f4de4fa8-ad5c-45c9-a804-0483309de9f9",
        "Hitmakr": "afac07d2-6c0e-42ae-9dd8-1fff68ca6a49",
    }
    
    # 请求 URL
    BASE_URL = "https://loyalty.campnetwork.xyz"
    COMPLETE_URL_TEMPLATE = f"{BASE_URL}/api/loyalty/rules/{{quest_id}}/complete"
    STATUS_URL = f"{BASE_URL}/api/loyalty/rules/status"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.completed_quests = []  # 当前会话中已完成的任务列表
        self.quest_status = {}  # 所有任务的状态
        self.user_id = kwargs.get('user_id')  # 用户 ID
    
    def set_user_id(self, user_id: str) -> None:
        """
        设置用户 ID
        
        参数:
            user_id: 用户 ID
        """
        self.user_id = user_id
    
    async def get_status_params(self) -> Dict[str, str]:
        """
        获取任务状态请求参数
        
        返回:
            状态请求参数
        """
        if not self.user_id:
            logger.error(f"{self.user} 尝试获取状态参数但没有用户 ID")
            return {}
            
        return {
            "userId": self.user_id,
            "websiteId": "32afc5c9-f0fb-4938-9572-775dee0b4a2b",
            "organizationId": "26a1764f-5637-425e-89fa-2f3fb86e758c"
        }
    
    async def check_quests_status(self) -> Dict:
        """
        检查所有任务的状态
        
        返回:
            任务状态
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
            logger.info(f"{self.user} 已获取任务状态（共 {len(response.get('rules', []))} 个）")
            return response
        else:
            logger.error(f"{self.user} 无法获取任务状态: {response}")
            return {}

    async def get_db_completed_quests(self) -> List[str]:
        """
        从数据库获取已完成任务列表
        
        返回:
            已完成任务的 ID 列表
        """
        try:
            async with Session() as session:
                db = DB(session=session)
                completed_quests = await db.get_completed_quests(self.user.id)
                
                # 更新当前会话中已完成的任务列表（任务名称）
                self.completed_quests = [
                    quest_name for quest_name, quest_id in self.QUEST_IDS.items() 
                    if quest_id in completed_quests
                ]
                
                return completed_quests
                
        except Exception as e:
            logger.error(f"{self.user} 从数据库获取已完成任务时出错: {e}")
            return []

    async def get_incomplete_quests(self) -> List[str]:
        """
        使用数据库数据获取未完成任务列表
        
        返回:
            未完成任务列表（名称）
        """
        # 从数据库获取已完成任务
        completed_quests_ids = await self.get_db_completed_quests()
        
        # 形成未完成任务列表
        incomplete_quests = []
        
        for quest_name, quest_id in self.QUEST_IDS.items():
            # 检查任务 ID 是否不在已完成列表中
            if quest_id not in completed_quests_ids:
                incomplete_quests.append(quest_name)
        
        logger.info(f"{self.user} 未完成任务 ({len(incomplete_quests)}): {', '.join(incomplete_quests) if incomplete_quests else '无'}")
        return incomplete_quests

    async def mark_quest_completed(self, quest_name: str) -> bool:
        """
        在数据库中标记任务为已完成
        
        参数:
            quest_name: 任务名称
            
        返回:
            成功状态
        """
        try:
            async with Session() as session:
                db = DB(session=session)
                result = await db.mark_quest_completed(self.user.id, quest_name)
                
                if result:
                    # 添加到本地已完成任务列表
                    if quest_name not in self.completed_quests:
                        self.completed_quests.append(quest_name)
                        
                    return True
                else:
                    return False
                    
        except Exception as e:
            logger.error(f"{self.user} 标记任务 {quest_name} 为已完成时出错: {e}")
            return False
    
    async def is_quest_completed(self, quest_name: str) -> bool:
        """
        检查任务是否已完成
        
        参数:
            quest_name: 任务名称
            
        返回:
            完成状态
        """
        # 首先检查本地已完成任务列表
        if quest_name in self.completed_quests:
            return True
            
        # 然后检查数据库
        try:
            async with Session() as session:
                db = DB(session=session)
                return await db.is_quest_completed(self.user.id, quest_name)
                
        except Exception as e:
            logger.error(f"{self.user} 检查任务 {quest_name} 状态时出错: {e}")
            return False

    async def complete_quest(self, quest_name: str) -> bool:
        """
        完成指定任务
        
        参数:
            quest_name: 任务名称
            
        返回:
            成功状态
        """
        # 检查任务是否已完成
        if await self.is_quest_completed(quest_name):
            logger.info(f"{self.user} 任务 {quest_name} 已完成")
            return True
            
        # 获取任务 ID
        quest_id = self.QUEST_IDS.get(quest_name)
        if not quest_id:
            logger.error(f"{self.user} 未知任务: {quest_name}")
            return False
            
        # 构建完成 URL
        complete_url = self.COMPLETE_URL_TEMPLATE.format(quest_id=quest_id)
        
        # 发送完成请求
        success, response = await self.request(
            url=complete_url,
            method="POST"
        )
        
        if success:
            # 标记任务为已完成
            if await self.mark_quest_completed(quest_name):
                logger.success(f"{self.user} 成功完成任务: {quest_name}")
                return True
            else:
                logger.error(f"{self.user} 无法标记任务 {quest_name} 为已完成")
                return False
        else:
            logger.error(f"{self.user} 完成任务 {quest_name} 时出错: {response}")
            return False

    async def complete_all_quests(self, retry_failed: bool = True, max_retries: int = 3) -> Dict[str, bool]:
        """
        完成所有未完成任务
        
        参数:
            retry_failed: 是否重试失败的任务
            max_retries: 最大重试次数
            
        返回:
            任务完成结果
        """
        # 获取未完成任务列表
        incomplete_quests = await self.get_incomplete_quests()
        if not incomplete_quests:
            logger.info(f"{self.user} 没有未完成的任务")
            return {}
            
        results = {}
        failed_quests = []
        
        # 完成每个任务
        for quest_name in incomplete_quests:
            success = await self.complete_quest(quest_name)
            results[quest_name] = success
            
            if not success:
                failed_quests.append(quest_name)
                
        # 如果需要重试失败的任务
        if retry_failed and failed_quests:
            logger.info(f"{self.user} 重试失败的任务: {', '.join(failed_quests)}")
            
            for _ in range(max_retries):
                if not failed_quests:
                    break
                    
                # 复制失败任务列表，因为我们在迭代时会修改它
                current_failed = failed_quests.copy()
                failed_quests = []
                
                for quest_name in current_failed:
                    success = await self.complete_quest(quest_name)
                    results[quest_name] = success
                    
                    if not success:
                        failed_quests.append(quest_name)
                        
                if failed_quests:
                    # 在重试之间等待
                    await asyncio.sleep(5)
                    
        # 记录最终结果
        if failed_quests:
            logger.warning(f"{self.user} 以下任务未能完成: {', '.join(failed_quests)}")
        else:
            logger.success(f"{self.user} 所有任务已完成")
            
        return results

    async def complete_specific_quests(self, quest_names: List[str]) -> Dict[str, bool]:
        """
        完成指定的任务列表
        
        参数:
            quest_names: 要完成的任务名称列表
            
        返回:
            任务完成结果
        """
        results = {}
        failed_quests = []
        
        # 完成每个指定的任务
        for quest_name in quest_names:
            # 检查任务是否存在
            if quest_name not in self.QUEST_IDS:
                logger.error(f"{self.user} 未知任务: {quest_name}")
                results[quest_name] = False
                continue
                
            # 检查任务是否已完成
            if await self.is_quest_completed(quest_name):
                logger.info(f"{self.user} 任务 {quest_name} 已完成")
                results[quest_name] = True
                continue
                
            # 完成任务
            success = await self.complete_quest(quest_name)
            results[quest_name] = success
            
            if not success:
                failed_quests.append(quest_name)
                
        # 记录结果
        if failed_quests:
            logger.warning(f"{self.user} 以下任务未能完成: {', '.join(failed_quests)}")
        else:
            logger.success(f"{self.user} 所有指定任务已完成")
            
        return results
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        获取任务完成和积分统计
        
        返回:
            任务统计信息
        """
        # 获取任务状态
        status = await self.check_quests_status()
        if not status:
            return {"error": "无法获取任务状态"}
            
        # 获取已完成任务
        completed_quests = await self.get_db_completed_quests()
        
        # 计算统计信息
        total_quests = len(self.QUEST_IDS)
        completed_count = len(completed_quests)
        remaining_count = total_quests - completed_count
        
        return {
            "total_quests": total_quests,
            "completed_quests": completed_count,
            "remaining_quests": remaining_count,
            "completion_percentage": (completed_count / total_quests * 100) if total_quests > 0 else 0,
            "quest_status": status
        }
