import os
from loguru import logger
import random
import asyncio
from website import auth_client
from website.camp_client import CampNetworkClient
from typing import  List, Tuple 
from website.twitter import TwitterClient
from website.quest_client import QuestClient
from website.resource_manager import ResourceManager
from libs.eth_async.client import Client
from libs.eth_async.utils.utils import parse_proxy
from libs.eth_async.data.models import Networks
from utils.db_api_async.db_api import Session
from utils.db_api_async.models import User
from utils.db_api_async.db_activity import DB
from data import config
from data.config import ACTUAL_FOLLOWS_TWITTER, ACTUAL_UA
from data.models import Settings

settings = Settings()

# 从文件加载数据
private_file = config.PRIVATE_FILE
if os.path.exists(private_file):
    with open(private_file, 'r') as private_file:
        private = [line.strip() for line in private_file if line.strip()]
else:
    private = []

proxy_file = config.PROXY_FILE
if os.path.exists(proxy_file):
    with open(proxy_file, 'r') as proxy_file:
        proxys = [line.strip() for line in proxy_file if line.strip()]
else:
    proxys = []

twitter_file = config.TWITTER_FILE
if os.path.exists(twitter_file):
    with open(twitter_file, 'r') as twitter_file:
        twitter = [line.strip() for line in twitter_file if line.strip()]
else:
    twitter = []

async def add_wallets_db():
    """将钱包导入数据库"""
    if not private:
        logger.error("private.txt 文件中没有私钥")
        return

    logger.info(f'正在导入 {len(private)} 个钱包到数据库')
    for i in range(len(private)):
        user_agent = ACTUAL_UA
        private_key = private[i]
        proxy = proxys[i] if i < len(proxys) else None
        proxy = parse_proxy(proxy) if proxy else None
        twitter_token = twitter[i] if i < len(twitter) else None
        
        try:
            client = Client(private_key=private_key, network=Networks.Ethereum)
            public_key = client.account.address
            
            async with Session() as session:
                db = DB(session=session)
                success = await db.add_wallet(
                    private_key=private_key,
                    public_key=public_key,
                    proxy=proxy,
                    user_agent=user_agent,
                    twitter_token=twitter_token
                )
                
                if success:
                    logger.success(f"钱包 {public_key} 已添加到数据库")
                else:
                    logger.warning(f"钱包 {public_key} 已存在于数据库中")
        except Exception as e:
            logger.error(f"添加钱包时出错: {str(e)}")

    logger.success('钱包导入完成')
    return

async def process_wallet(wallet: User):
    """
    处理单个钱包的所有任务，包括资源错误处理
    
    参数:
        wallet: 钱包对象
        
    返回:
        成功状态
    """
    resource_manager = ResourceManager()
    settings = Settings()
    auto_replace, max_failures = settings.get_resource_settings()
    
    # 错误计数器
    proxy_errors = 0
    
    # 用于跟踪是否需要重试
    retry_with_new_proxy = True
    max_retries = 3
    retry_count = 0
    
    twitter_enabled = settings.twitter_enabled and wallet.twitter_token is not None
    
    # 获取未完成任务列表
    async with Session() as session:
        db = DB(session=session)
        completed_quests_ids = wallet.completed_quests.split(',') if wallet.completed_quests else []
        all_quests_ids = list(QuestClient.QUEST_IDS.values())
        
        # 过滤出尚未完成的任务
        incomplete_quests_ids = [quest_id for quest_id in all_quests_ids if quest_id not in completed_quests_ids]
        
        # 将任务 ID 转换回名称
        incomplete_quests = []
        for quest_id in incomplete_quests_ids:
            for quest_name, qid in QuestClient.QUEST_IDS.items():
                if qid == quest_id:
                    incomplete_quests.append(quest_name)
                    break
    
    # 获取所有 Twitter 任务（关注）列表
    twitter_follow_tasks = []
    if twitter_enabled:
        for account_name in settings.twitter_follow_accounts:
            quest_id = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {}).get(account_name)
            if quest_id and quest_id not in completed_quests_ids:
                twitter_follow_tasks.append(account_name)
    
    # 计算所有任务的总数
    total_tasks = len(incomplete_quests) + len(twitter_follow_tasks)
    
    if total_tasks == 0:
        logger.success(f"{wallet} 所有任务已完成")
        return True

    startup_min, startup_max = settings.get_wallet_startup_delay()
    delay = random.uniform(startup_min, startup_max)
    logger.info(f"钱包 {wallet} 将在 {int(delay)} 秒后启动")
    await asyncio.sleep(delay)
    while retry_with_new_proxy and retry_count < max_retries:
        try:
            # 如果是使用新代理重试，更新钱包数据
            if retry_count > 0:
                async with Session() as session:
                    wallet = await session.get(User, wallet.id)
                    if not wallet:
                        logger.error(f"无法获取 ID 为 {wallet.id} 的钱包更新数据")
                        return False
            
            logger.info(f'开始处理 {wallet} (尝试 {retry_count + 1}/{max_retries})')
            
            # 创建 CampNetwork 客户端
            camp_client = CampNetworkClient(user=wallet)
            
            # 在网站上登录
            auth_success = await camp_client.login()
            if not auth_success:
                logger.error(f"{wallet} 无法在 CampNetwork 上登录")
                
                # 检查问题是否与代理有关
                if "proxy" in str(auth_success).lower() or "connection" in str(auth_success).lower():
                    proxy_errors += 1
                    logger.warning(f"{wallet} 可能是代理问题 (错误 {proxy_errors}/{max_failures})")
                    
                    # 如果达到错误阈值，将代理标记为不良
                    if proxy_errors >= max_failures:
                        await resource_manager.mark_proxy_as_bad(wallet.id)
                        
                        # 如果启用了自动替换，尝试替换代理
                        if auto_replace:
                            success, message = await resource_manager.replace_proxy(wallet.id)
                            if success:
                                logger.info(f"{wallet} 代理已替换: {message}，正在重试...")
                                retry_count += 1
                                continue  # 使用新代理重试
                            else:
                                logger.error(f"{wallet} 无法替换代理: {message}")
                                retry_with_new_proxy = False  # 停止尝试
                                return False
                
                # 如果问题不是代理或没有自动替换，退出
                retry_with_new_proxy = False
                return False
            
            # 如果登录成功，停止重试循环
            retry_with_new_proxy = False
            
            # 检查是否启用 Twitter
            twitter_enabled = settings.twitter_enabled and wallet.twitter_token is not None
            
            # 获取未完成任务列表
            async with Session() as session:
                db = DB(session=session)
                completed_quests_ids = wallet.completed_quests.split(',') if wallet.completed_quests else []
                all_quests_ids = list(QuestClient.QUEST_IDS.values())
                
                # 过滤出尚未完成的任务
                incomplete_quests_ids = [quest_id for quest_id in all_quests_ids if quest_id not in completed_quests_ids]
                
                # 将任务 ID 转换回名称
                incomplete_quests = []
                for quest_id in incomplete_quests_ids:
                    for quest_name, qid in QuestClient.QUEST_IDS.items():
                        if qid == quest_id:
                            incomplete_quests.append(quest_name)
                            break
            
            # 获取所有 Twitter 任务（关注）列表
            twitter_follow_tasks = []
            if twitter_enabled:
                for account_name in settings.twitter_follow_accounts:
                    quest_id = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {}).get(account_name)
                    if quest_id and quest_id not in completed_quests_ids:
                        twitter_follow_tasks.append(account_name)
            
            # 计算所有任务的总数
            total_tasks = len(incomplete_quests) + len(twitter_follow_tasks)
            
            if total_tasks == 0:
                logger.success(f"{wallet} 所有任务已完成")
                return True
            
            logger.info(f"{wallet} 找到 {len(incomplete_quests)} 个常规任务和 {len(twitter_follow_tasks)} 个 Twitter 任务需要完成")
            
            # 获取常规任务的延迟设置
            regular_min_delay, regular_max_delay = settings.get_quest_delay()
            
            # 完成常规任务
            regular_completed = 0
            if incomplete_quests:
                logger.info(f"{wallet} 正在完成常规任务 ({len(incomplete_quests)})")
                
                # 随机打乱任务列表
                random.shuffle(incomplete_quests)
                
                for quest_name in incomplete_quests:
                    try:
                        logger.info(f"{wallet} 正在完成任务 {quest_name}")
                        result = await camp_client.quest_client.complete_quest(quest_name)
                        
                        if result:
                            logger.success(f"{wallet} 成功完成任务 {quest_name}")
                            regular_completed += 1
                        else:
                            logger.warning(f"{wallet} 无法完成任务 {quest_name}")
                        
                        # 任务之间的延迟
                        delay = random.uniform(regular_min_delay, regular_max_delay)
                        logger.info(f"{wallet} 任务之间的延迟 {int(delay)} 秒")
                        await asyncio.sleep(delay)
                        
                    except Exception as e:
                        logger.error(f"{wallet} 执行任务 {quest_name} 时出错: {str(e)}")
                        
                        # 检查是否可能是代理问题
                        if "proxy" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                            proxy_errors += 1
                            logger.warning(f"{wallet} 可能是代理问题 (错误 {proxy_errors}/{max_failures})")
                            
                            # 如果达到错误阈值，将代理标记为不良
                            if proxy_errors >= max_failures:
                                await resource_manager.mark_proxy_as_bad(wallet.id)
                        
                        await asyncio.sleep(regular_min_delay)
                        continue
            
            # 完成 Twitter 任务，如果启用且有任务
            twitter_completed_count = 0
            if twitter_enabled and twitter_follow_tasks:
                # 添加任务之间的延迟，如果有常规任务
                if regular_quests:
                    twitter_delay = random.uniform(regular_min_delay, regular_max_delay)
                    logger.info(f"{wallet} 等待 {int(twitter_delay)} 秒开始 Twitter 任务")
                    await asyncio.sleep(twitter_delay)
                
                # 通过公共函数完成 Twitter 任务
                twitter_result, twitter_completed_count = await process_twitter_tasks(
                    wallet=wallet,
                    camp_client=camp_client,
                    resource_manager=resource_manager,
                    settings=settings,
                    follow_accounts=twitter_follow_tasks
                )
                
                if twitter_result:
                    logger.success(f"{wallet} 成功完成 {twitter_completed_count} 个 Twitter 任务")
                else:
                    logger.warning(f"{wallet} Twitter 任务完成部分: {twitter_completed_count} 个")
            
            # 获取已完成任务列表进行检查
            async with Session() as session:
                db = DB(session=session)
                final_completed_quests = await db.get_completed_quests(wallet.id)
                
            # 输出最终结果
            completed_count = regular_completed + twitter_completed_count
            total_requested = len(regular_quests) + len(twitter_follow_tasks)
            
            logger.success(f"{wallet} 任务完成: {completed_count}/{total_requested} 请求的任务")
            logger.info(f"{wallet} 成功完成常规任务: {regular_completed} 个")
            logger.info(f"{wallet} 成功完成 Twitter 任务: {twitter_completed_count} 个")
            
            # 如果成功完成至少一个任务，则认为任务成功
            return completed_count > 0
                
        except Exception as e:
            logger.error(f"{wallet} 处理时出错: {str(e)}")
            
            # 检查是否可能是代理问题
            if "proxy" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                proxy_errors += 1
                logger.warning(f"{wallet} 可能是代理问题 (错误 {proxy_errors}/{max_failures})")
                
                # 如果达到错误阈值，将代理标记为不良
                if proxy_errors >= max_failures:
                    await resource_manager.mark_proxy_as_bad(wallet.id)
                    
                    # 如果启用了自动替换，尝试替换代理
                    if auto_replace:
                        success, message = await resource_manager.replace_proxy(wallet.id)
                        if success:
                            logger.info(f"{wallet} 代理已替换: {message}，正在重试...")
                            retry_count += 1
                            continue  # 使用新代理重试
                        else:
                            logger.error(f"{wallet} 无法替换代理: {message}")
                else:
                    await asyncio.sleep(10)
                    retry_count += 1
                    continue
            
            # 如果问题不是代理或没有替换代理
            return False
    
    # 如果所有尝试都失败了
    if retry_count >= max_retries:
        logger.error(f"{wallet} 所有 {max_retries} 次重试失败")
    
    return False

async def process_twitter_tasks(wallet: User, camp_client, resource_manager, settings, follow_accounts: List[str]) -> Tuple[bool, int]:
    """
    Separate function for processing Twitter tasks with retries and correct token replacement
    
    Args:
        wallet: Wallet object
        camp_client: CampNetwork client
        resource_manager: Resources manager
        settings: Settings
        follow_accounts: List of accounts to follow
        
    Returns:
        Tuple[success, completed_count]: Success status and completed tasks count
    """
    twitter_errors = 0
    max_failures = settings.resources_max_failures
    auto_replace = settings.resources_auto_replace
    max_twitter_retries = 4
    twitter_retry_count = 0
    completed_count = 0
    twitter_min_delay, twitter_max_delay = settings.get_twitter_quest_delay()
    
    # Check for Twitter restrictions
    daily_limit_reached = False
    random.shuffle(follow_accounts)
    
    # For each attempt to perform Twitter tasks
    while twitter_retry_count < max_twitter_retries:
        logger.info(f"{wallet} 正在执行 Twitter 任务 (尝试 {twitter_retry_count + 1}/{max_twitter_retries})")
        
        # Variable to track initialized client
        twitter_client = None
        
        try:
            # Create Twitter client
            twitter_client = TwitterClient(
                user=wallet,
                auth_client=camp_client.auth_client,
                twitter_auth_token=wallet.twitter_token
            )
            
            # IMPORTANT: Initialize client
            init_success = await twitter_client.initialize()
            if not init_success:
                logger.error(f"{wallet} 无法初始化 Twitter 客户端")
                
                # Add delay after error
                error_delay = random.uniform(2, 3)
                logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
                await asyncio.sleep(error_delay)
                
                # If unable to initialize, try to replace token
                if auto_replace and twitter_retry_count < max_failures:
                    logger.warning(f"{wallet} 无法初始化 Twitter 客户端，尝试替换令牌")
                    
                    # Mark token as bad
                    await resource_manager.mark_twitter_as_bad(wallet.id)
                    
                    success, message = await resource_manager.replace_twitter(wallet.id)
                    if success:
                        logger.info(f"{wallet} Twitter 令牌已替换到数据库: {message}")
                        
                        # Update token in wallet from database
                        async with Session() as session:
                            updated_wallet = await session.get(User, wallet.id)
                            if updated_wallet and updated_wallet.twitter_token:
                                # Use token replacement function
                                replace_success = await twitter_client.replace_twitter_token(updated_wallet.twitter_token)
                                if replace_success:
                                    logger.success(f"{wallet} 成功替换 Twitter 令牌到网站")
                                    wallet.twitter_token = updated_wallet.twitter_token
                                    # Break current retry loop
                                    twitter_retry_count += 1
                                    continue
                                else:
                                    logger.error(f"{wallet} 无法替换 Twitter 令牌到网站")
                                    # Continue with next main iteration
                                    twitter_retry_count += 1
                                    continue
                    else:
                        logger.error(f"{wallet} 无法替换 Twitter 令牌: {message}")
                        await resource_manager.mark_twitter_as_bad(wallet.id)
                        return False, completed_count
                else:
                    logger.error(f"{wallet} 无法初始化 Twitter 客户端")
                    await resource_manager.mark_twitter_as_bad(wallet.id)
                    return False, completed_count
            
            # Check Twitter connection and reconnect if necessary
            connect_attempts = 0
            max_connect_attempts = 3  # Maximum number of connection attempts
            
            while connect_attempts < max_connect_attempts:
                twitter_connected = await twitter_client.check_twitter_connection_status()
                
                if twitter_connected:
                    logger.success(f"{wallet} Twitter 帐户已连接到 CampNetwork")
                    break
                
                logger.info(f"{wallet} Twitter 未连接，正在连接 (尝试 {connect_attempts + 1}/{max_connect_attempts})")
                
                # Connect Twitter account to CampNetwork
                connect_success = await twitter_client.connect_twitter_to_camp()
                
                if connect_success:
                    logger.success(f"{wallet} 成功连接到 Twitter 到 CampNetwork")
                    break
                else:
                    connect_attempts += 1
                    logger.error(f"{wallet} 无法连接到 Twitter 到 CampNetwork (尝试 {connect_attempts}/{max_connect_attempts})")
                    
                    # Add delay after error
                    error_delay = random.uniform(3, 5)  # Increased delay for connection
                    logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
                    await asyncio.sleep(error_delay)
                    
                    # Check if there could be a Twitter token problem
                    if connect_attempts >= max_connect_attempts:
                        last_error = getattr(twitter_client, 'last_error', '')
                        if last_error and any(x in str(last_error).lower() for x in ["unauthorized", "auth", "token", "login", "limit", "unable to follow"]):
                            logger.warning(f"{wallet} Twitter 令牌问题: {last_error}")
                            await resource_manager.mark_twitter_as_bad(wallet.id)
                            
                            # If auto-replace is enabled, try to replace token
                            if auto_replace and twitter_retry_count < max_twitter_retries - 1:
                                success, message = await resource_manager.replace_twitter(wallet.id)
                                if success:
                                    logger.info(f"{wallet} Twitter 令牌已替换到数据库: {message}, 正在网站上执行替换...")
                                    
                                    # Get new token from database
                                    async with Session() as session:
                                        updated_wallet = await session.get(User, wallet.id)
                                        if updated_wallet and updated_wallet.twitter_token:
                                            # Use token replacement function
                                            replace_success = await twitter_client.replace_twitter_token(updated_wallet.twitter_token)
                                            if replace_success:
                                                logger.success(f"{wallet} 成功替换 Twitter 令牌到网站")
                                                wallet.twitter_token = updated_wallet.twitter_token
                                                # Break current retry loop
                                                break
                                            else:
                                                logger.error(f"{wallet} 无法替换 Twitter 令牌到网站")
                                                # Continue with next main iteration
                                                twitter_retry_count += 1
                                                break
                                else:
                                    logger.error(f"{wallet} 无法替换 Twitter 令牌: {message}")
                                    return False, completed_count
            
            # Check if Twitter connected after all attempts
            if connect_attempts >= max_connect_attempts:
                if twitter_retry_count < max_twitter_retries - 1:
                    # Still have main loop attempts, continue with next iteration
                    twitter_retry_count += 1
                    continue
                else:
                    logger.error(f"{wallet} 无法连接到 Twitter 到 CampNetwork 所有尝试")
                    return False, completed_count
            
            # If daily limit reached, skip task execution
            if daily_limit_reached:
                logger.warning(f"{wallet} 达到 Twitter 每日限制，跳过剩余任务")
                # Return partial success status if tasks were completed
                return completed_count > 0, completed_count
            
            # Process each account as separate task
            for i, account_name in enumerate(follow_accounts):
                try:
                    # Get task ID for this account
                    quest_id = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {}).get(account_name)
                    if not quest_id:
                        logger.warning(f"{wallet} 没有 ID 任务订阅 {account_name}")
                        continue
                    
                    # Check if task already completed in database
                    async with Session() as session:
                        db = DB(session=session)
                        if await db.is_quest_completed(wallet.id, quest_id):
                            logger.info(f"{wallet} 订阅任务 {account_name} 已完成")
                            completed_count += 1
                            continue
                    
                    logger.info(f"{wallet} 正在执行订阅任务 {account_name}")
                    
                    # Use follow_account method with Twitter restrictions handling
                    follow_success, error_message, already_following = await twitter_client.follow_account(account_name)
                    
                    # Process case when subscription failed and we were not subscribed before
                    if not follow_success and not already_following:
                        if error_message:
                            if "订阅限制" in error_message or "每日限制" in error_message:
                                logger.warning(f"{wallet} {error_message}")
                                daily_limit_reached = True
                                # Break execution of remaining tasks
                                break
                            else:
                                logger.error(f"{wallet} 订阅 {account_name} 时出错: {error_message}")
                                # Add delay after error
                                error_delay = random.uniform(30, 60)
                                logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
                                await asyncio.sleep(error_delay)
                                continue
                    
                    # If subscription successful or we were already subscribed, try to execute task
                    if follow_success or already_following:
                        # If we were already subscribed, mark it in log
                        if already_following:
                            logger.info(f"{wallet} 已订阅 {account_name}，尝试执行任务")
                    
                        # Send request to execute task with retries
                        complete_url = f"{camp_client.auth_client.BASE_URL}/api/loyalty/rules/{quest_id}/complete"
                        
                        headers = await camp_client.auth_client.get_headers({
                            'Accept': 'application/json, text/plain, */*',
                            'Content-Type': 'application/json',
                            'Origin': 'https://loyalty.campnetwork.xyz',
                        })
                        
                        # Make several attempts to execute task
                        complete_attempts = 0
                        max_complete_attempts = 3  # Maximum number of task execution attempts
                        
                        while complete_attempts < max_complete_attempts:
                            success, response = await camp_client.auth_client.request(
                                url=complete_url,
                                method="POST",
                                json_data={},
                                headers=headers
                            )
                            
                            if success:
                                logger.success(f"{wallet} 成功完成订阅任务 {account_name}")
                                completed_count += 1
                                
                                # Mark task as completed in database
                                async with Session() as session:
                                    db = DB(session=session)
                                    await db.mark_quest_completed(wallet.id, quest_id)
                                
                                # Success, exit retry loop
                                break
                            
                            elif isinstance(response, dict) and response.get("message") == "You have already been rewarded":
                                logger.info(f"{wallet} 订阅任务 {account_name} 已标记为已完成")
                                completed_count += 1
                                
                                # Mark task as completed in database
                                async with Session() as session:
                                    db = DB(session=session)
                                    await db.mark_quest_completed(wallet.id, quest_id)
                                
                                # Success, exit retry loop
                                break
                            
                            else:
                                complete_attempts += 1
                                logger.warning(f"{wallet} 无法完成订阅任务 {account_name} (尝试 {complete_attempts}/{max_complete_attempts})")
                                
                                if complete_attempts < max_complete_attempts:
                                    # Add delay before next attempt
                                    retry_delay = random.uniform(5, 10)  # Increased delay between attempts
                                    logger.info(f"{wallet} 等待 {retry_delay:.1f} 秒后重试")
                                    await asyncio.sleep(retry_delay)
                                else:
                                    logger.error(f"{wallet} 无法完成订阅任务 {account_name} 后 {max_complete_attempts} 次尝试")
                    
                    # Add delay between tasks if this is not the last account and limit not reached
                    if not daily_limit_reached and i < len(follow_accounts) - 1:
                        delay = random.uniform(twitter_min_delay, twitter_max_delay)
                        logger.info(f"{wallet} 等待 {int(delay)} 秒后重试")
                        await asyncio.sleep(delay)
                    
                except Exception as e:
                    logger.error(f"{wallet} 处理任务 {account_name} 时出错: {str(e)}")
                    
                    # Add delay after error
                    error_delay = random.uniform(2, 3)
                    logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
                    await asyncio.sleep(error_delay)
                    
                    # Check for Twitter restrictions
                    if "limit" in str(e).lower() or "unable to follow" in str(e).lower():
                        logger.warning(f"{wallet} 达到 Twitter 限制，跳过剩余订阅")
                        daily_limit_reached = True
                        break
                    
                    # Check if there could be a Twitter token problem
                    if any(x in str(e).lower() for x in ["unauthorized", "authentication", "token", "login", "banned"]):
                        twitter_errors += 1
                        logger.warning(f"{wallet} 可能是 Twitter 令牌问题 (错误 {twitter_errors}/{max_failures})")
                        
                        # If reached error threshold, mark token as bad
                        if twitter_errors >= max_failures:
                            await resource_manager.mark_twitter_as_bad(wallet.id)
                            
                            # If auto-replace is enabled, try to replace token
                            if auto_replace and twitter_retry_count < max_twitter_retries - 1:
                                # First disconnect current Twitter account
                                await twitter_client.disconnect_twitter()
                                
                                # Then replace token in database
                                success, message = await resource_manager.replace_twitter(wallet.id)
                                if success:
                                    logger.info(f"{wallet} Twitter 令牌已替换到数据库: {message}, 正在网站上执行替换...")
                                    
                                    # Get new token from database
                                    async with Session() as session:
                                        updated_wallet = await session.get(User, wallet.id)
                                        if updated_wallet and updated_wallet.twitter_token:
                                            # Use token replacement function
                                            replace_success = await twitter_client.replace_twitter_token(updated_wallet.twitter_token)
                                            if replace_success:
                                                logger.success(f"{wallet} 成功替换 Twitter 令牌到网站")
                                                wallet.twitter_token = updated_wallet.twitter_token
                                                # Increase retry counter and break current loop
                                                twitter_retry_count += 1
                                                # Close current Twitter client
                                                await twitter_client.close()
                                                # Move to next attempt with new token
                                                break
                                            else:
                                                logger.error(f"{wallet} 无法替换 Twitter 令牌到网站")
                                                # If unable to replace token on website, update token in object
                                                # for next attempt, but do not use replace_twitter_token
                                                wallet.twitter_token = updated_wallet.twitter_token
                                                twitter_retry_count += 1
                                                await twitter_client.close()
                                                break
                                else:
                                    logger.error(f"{wallet} 无法替换 Twitter 令牌: {message}")
            
            # Close Twitter client after processing all accounts
            if twitter_client:
                await twitter_client.close()
            
            # If Twitter limit reached or all tasks completed, break retry loop
            if daily_limit_reached or completed_count == len(follow_accounts):
                break
            
            # If token replaced and moved to next attempt, skip below code
            if twitter_retry_count > 0:
                continue
                
            # If no token replaced and not all tasks completed, but passed all accounts,
            # increase retry counter for next iteration
            twitter_retry_count += 1
            
        except Exception as e:
            logger.error(f"{wallet} 执行 Twitter 任务时出错: {str(e)}")
            
            # Add delay after error
            error_delay = random.uniform(2, 3)
            logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
            await asyncio.sleep(error_delay)
            
            # Close Twitter client if it was created
            if twitter_client:
                await twitter_client.close()
            
            # Check if there could be a Twitter token problem
            if any(x in str(e).lower() for x in ["unauthorized", "authentication", "token", "login", "banned"]):
                twitter_errors += 1
                
                # If reached error threshold, mark token as bad
                if twitter_errors >= max_failures:
                    await resource_manager.mark_twitter_as_bad(wallet.id)
                    
                    # If auto-replace is enabled, try to replace token
                    if auto_replace and twitter_retry_count < max_twitter_retries - 1:
                        success, message = await resource_manager.replace_twitter(wallet.id)
                        if success:
                            logger.info(f"{wallet} Twitter 令牌已替换到数据库: {message}, 正在重试...")
                            
                            # Update token in wallet
                            async with Session() as session:
                                updated_wallet = await session.get(User, wallet.id)
                                if updated_wallet and updated_wallet.twitter_token:
                                    # Save new token for next attempt
                                    wallet.twitter_token = updated_wallet.twitter_token
                                    # Increase retry counter and continue
                                    twitter_retry_count += 1
                                    continue
                        else:
                            logger.error(f"{wallet} 无法替换 Twitter 令牌: {message}")
            
            # Increase retry counter
            twitter_retry_count += 1
    
    # Return success status and completed tasks count
    return completed_count > 0, completed_count

async def process_wallet_with_specific_quests(wallet: User, quest_list, twitter_follows=None):
    """
    Executes specified tasks for one wallet with resource error handling
    
    Args:
        wallet: Wallet object
        quest_list: List of regular tasks to execute
        twitter_follows: List of Twitter accounts to follow (optional)
        
    Returns:
        Success status
    """
    resource_manager = ResourceManager()
    settings = Settings()
    auto_replace, max_failures = settings.get_resource_settings()
    
    # Error counters
    proxy_errors = 0
    
    # For tracking whether to retry
    retry_with_new_proxy = True
    max_retries = 3
    retry_count = 0
    
    startup_min, startup_max = settings.get_wallet_startup_delay()
    delay = random.uniform(startup_min, startup_max)
    logger.info(f"钱包 {wallet} 将在 {int(delay)} 秒后启动")
    await asyncio.sleep(delay)
    # If twitter_follows not passed, initialize empty list
    if twitter_follows is None:
        twitter_follows = []
    
    while retry_with_new_proxy and retry_count < max_retries:
        try:
            # If this is a retry with a new proxy, update wallet data
            if retry_count > 0:
                async with Session() as session:
                    wallet = await session.get(User, wallet.id)
                    if not wallet:
                        logger.error(f"无法获取 ID 为 {wallet.id} 的钱包更新数据")
                        return False
            
            # Define if there are Twitter tasks to execute
            has_twitter_tasks = "TwitterFollow" in quest_list or twitter_follows
            
            logger.info(f'开始处理 {wallet} 任务: {", ".join(quest_list)} ' +
                       (f'和 Twitter 订阅: {len(twitter_follows)}' if twitter_follows else '') +
                       f' (尝试 {retry_count + 1}/{max_retries})')
            
            # Create CampNetwork client
            camp_client = CampNetworkClient(user=wallet)
            
            # Login to website
            auth_success = await camp_client.login()
            if not auth_success:
                logger.error(f"{wallet} 无法在 CampNetwork 上登录")
                
                # Check if problem is with proxy
                if "proxy" in str(auth_success).lower() or "connection" in str(auth_success).lower():
                    proxy_errors += 1
                    logger.warning(f"{wallet} 可能是代理问题 (错误 {proxy_errors}/{max_failures})")
                    
                    # Add delay after error
                    error_delay = random.uniform(2, 3)
                    logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
                    await asyncio.sleep(error_delay)
                    
                    # If reached error threshold, mark proxy as bad
                    if proxy_errors >= max_failures:
                        await resource_manager.mark_proxy_as_bad(wallet.id)
                        
                        # If auto-replace is enabled, try to replace proxy
                        if auto_replace:
                            success, message = await resource_manager.replace_proxy(wallet.id)
                            if success:
                                logger.info(f"{wallet} 代理已替换: {message}，正在重试...")
                                retry_count += 1
                                continue  # Use new proxy retry
                            else:
                                logger.error(f"{wallet} 无法替换代理: {message}")
                                retry_with_new_proxy = False  # Stop trying
                                return False
                
                # If problem is not with proxy or no auto-replace, exit
                retry_with_new_proxy = False
                return False
            
            # If login successful, stop retry loop
            retry_with_new_proxy = False
            
            # Check if Twitter enabled
            twitter_enabled = settings.twitter_enabled and wallet.twitter_token is not None
            
            # Separate tasks into regular and Twitter
            regular_quests = []
            
            # Filter tasks for Twitter and regular
            for quest in quest_list:
                if quest != "TwitterFollow":  # Skip general Twitter task marker
                    # Check if task exists and not completed
                    quest_id = QuestClient.QUEST_IDS.get(quest)
                    if quest_id:
                        async with Session() as session:
                            db = DB(session=session)
                            if not await db.is_quest_completed(wallet.id, quest_id):
                                regular_quests.append(quest)
            
            # Get task statistics for display
            total_tasks = len(regular_quests) + len(twitter_follows)
            if total_tasks == 0:
                logger.success(f"{wallet} 所有选定任务已完成")
                return True
                
            logger.info(f"{wallet} 找到 {len(regular_quests)} 个常规任务和 {len(twitter_follows)} Twitter 任务需要完成")
            
            # Get delay settings
            regular_min_delay, regular_max_delay = settings.get_quest_delay()
            
            # Execute regular tasks in random order
            regular_completed = 0
            if regular_quests:
                # Shuffle tasks for randomization
                random.shuffle(regular_quests)
                
                logger.info(f"{wallet} 正在执行 {len(regular_quests)} 常规任务")
                
                for quest_name in regular_quests:
                    try:
                        logger.info(f"{wallet} 正在执行任务 {quest_name}")
                        result = await camp_client.quest_client.complete_quest(quest_name)
                        
                        if result:
                            logger.success(f"{wallet} 成功完成任务 {quest_name}")
                            regular_completed += 1
                        else:
                            logger.warning(f"{wallet} 无法完成任务 {quest_name}")
                            
                            # Add delay after error
                            error_delay = random.uniform(2, 3)
                            logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
                            await asyncio.sleep(error_delay)
                        
                        # Task delay between tasks
                        if quest_name != regular_quests[-1]:  # If this is not the last task
                            delay = random.uniform(regular_min_delay, regular_max_delay)
                            logger.info(f"{wallet} 等待 {int(delay)} 秒后重试")
                            await asyncio.sleep(delay)
                        
                    except Exception as e:
                        logger.error(f"{wallet} 执行任务 {quest_name} 时出错: {str(e)}")
                        
                        # Add delay after error
                        error_delay = random.uniform(2, 3)
                        logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
                        await asyncio.sleep(error_delay)
                        
                        # Check if there could be a proxy problem
                        if "proxy" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                            proxy_errors += 1
                            logger.warning(f"{wallet} 可能是代理问题 (错误 {proxy_errors}/{max_failures})")
                            
                            # If reached error threshold, mark proxy as bad
                            if proxy_errors >= max_failures:
                                await resource_manager.mark_proxy_as_bad(wallet.id)
                        
                        await asyncio.sleep(regular_min_delay)
                        continue
            
            # Execute Twitter tasks if they exist and Twitter enabled
            twitter_completed_count = 0
            if twitter_enabled and has_twitter_tasks and twitter_follows:
                # Add delay before Twitter tasks if there were regular tasks
                if regular_quests:
                    twitter_delay = random.uniform(regular_min_delay, regular_max_delay)
                    logger.info(f"{wallet} 等待 {int(twitter_delay)} 秒开始 Twitter 任务")
                    await asyncio.sleep(twitter_delay)
                
                # Execute Twitter tasks through public function
                twitter_result, twitter_completed_count = await process_twitter_tasks(
                    wallet=wallet,
                    camp_client=camp_client,
                    resource_manager=resource_manager,
                    settings=settings,
                    follow_accounts=twitter_follows
                )
                
                if twitter_result:
                    logger.success(f"{wallet} 成功完成 {twitter_completed_count} 个 Twitter 任务")
                else:
                    logger.warning(f"{wallet} Twitter 任务完成部分: {twitter_completed_count} 个")
            
            # Get completed tasks list for checking
            async with Session() as session:
                db = DB(session=session)
                final_completed_quests = await db.get_completed_quests(wallet.id)
                
            # Output final results
            completed_count = regular_completed + twitter_completed_count
            total_requested = len(regular_quests) + len(twitter_follows)
            
            logger.success(f"{wallet} 任务完成: {completed_count}/{total_requested} 请求的任务")
            logger.info(f"{wallet} 成功完成常规任务: {regular_completed} 个")
            logger.info(f"{wallet} 成功完成 Twitter 任务: {twitter_completed_count} 个")
            
            # If at least one task completed, consider task successful
            return completed_count > 0
                
        except Exception as e:
            logger.error(f"{wallet} 处理时出错: {str(e)}")
            
            # Add delay after error
            error_delay = random.uniform(2, 3)
            logger.info(f"{wallet} 等待 {error_delay:.1f} 秒后重试")
            await asyncio.sleep(error_delay)
            
            # Check if there could be a proxy problem
            if "proxy" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                proxy_errors += 1
                logger.warning(f"{wallet} 可能是代理问题 (错误 {proxy_errors}/{max_failures})")
                
                # If reached error threshold, mark proxy as bad
                if proxy_errors >= max_failures:
                    await resource_manager.mark_proxy_as_bad(wallet.id)
                    
                    # If auto-replace is enabled, try to replace proxy
                    if auto_replace:
                        success, message = await resource_manager.replace_proxy(wallet.id)
                        if success:
                            logger.info(f"{wallet} 代理已替换: {message}，正在重试...")
                            retry_count += 1
                            continue  # Use new proxy retry
                        else:
                            logger.error(f"{wallet} 无法替换代理: {message}")
                else:
                    await asyncio.sleep(10)
                    retry_count += 1
                    continue
            
            # If problem is not with proxy or unable to replace proxy
            return False
    
    # If all attempts failed
    if retry_count >= max_retries:
        logger.error(f"{wallet} 所有 {max_retries} 次重试失败")
    
    return False

async def complete_all_wallets_quests():
    """Executes tasks for all wallets"""
    try:
        # Get wallets list from database
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()
        
        if not all_wallets:
            logger.error("没有钱包在数据库中。首先导入钱包。")
            return
        
        # Define wallets range for processing from settings
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]
        
        # Display information about wallets for processing
        logger.info(f"找到 {len(all_wallets)} 个钱包")
        logger.info(f"将处理 {len(wallets)} 个钱包 (从 {wallet_start+1} 到 {wallet_start+len(wallets)})")
        
        # Shuffle wallets for randomization order
        random.shuffle(wallets)
        
        # Get wallets delay settings
        
        # Create tasks for all wallets
        tasks = []
        for i, wallet in enumerate(wallets):
            # Add random delay between wallet processing starts
            
            # Create task for processing wallet
            task = asyncio.create_task(process_wallet(wallet))
            tasks.append(task)
        
        # If no tasks, exit
        if not tasks:
            logger.warning("没有钱包要处理")
            return
            
        # Start all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        success_count = sum(1 for result in results if result is True)
        error_count = sum(1 for result in results if isinstance(result, Exception) or result is False)
        
        logger.info(f"处理完成: 成功 {success_count}，出错 {error_count}")
        
    except Exception as e:
        logger.error(f"执行所有钱包任务时出错: {str(e)}")

async def complete_specific_quests():
    """Executes specified tasks for all wallets with settings"""
    try:
        # Get wallets list from database
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()
        
        if not all_wallets:
            logger.error("没有钱包在数据库中。首先导入钱包。")
            return
        
        # Define wallets range for processing from settings
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]
        
        # Shuffle wallets for randomization
        random.shuffle(wallets)
        
        logger.info(f"找到 {len(all_wallets)} 个钱包")
        logger.info(f"将处理 {len(wallets)} 个钱包 (从 {wallet_start+1} 到 {wallet_start+len(wallets)})")
        
        # Get list of available regular tasks
        quests = list(QuestClient.QUEST_IDS.keys())
        
        # Add Twitter tasks with more understandable names
        if settings.twitter_enabled:
            twitter_accounts = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {})
            for account, quest_id in twitter_accounts.items():
                quests.append(f"Twitter Follow: @{account}")
        
        print("\n=== 可用任务 ===")
        for i, quest_name in enumerate(quests, 1):
            print(f"{i}. {quest_name}")
        
        print("\n输入任务编号，用逗号分隔（或输入 'all' 执行所有）：")
        quest_input = input("> ").strip()
        
        if quest_input.lower() == 'all':
            selected_quests = quests
        else:
            try:
                # Parse entered numbers
                quest_numbers = [int(num.strip()) for num in quest_input.split(",") if num.strip()]
                selected_quests = [quests[num-1] for num in quest_numbers if 1 <= num <= len(quests)]
                
                if not selected_quests:
                    logger.error("未选择任何任务")
                    return
            except (ValueError, IndexError):
                logger.error(f"输入错误。任务编号必须为 1 到 {len(quests)}")
                return
        
        logger.info(f"选择任务: {', '.join(selected_quests)}")
        
        # Convert Twitter Follow task names to regular format for processing
        processed_quests = []
        twitter_follows = []
        
        for quest in selected_quests:
            if quest.startswith("Twitter Follow: @"):
                account_name = quest.replace("Twitter Follow: @", "")
                twitter_follows.append(account_name)
            else:
                processed_quests.append(quest)
        
        # If Twitter tasks selected, add general TwitterFollow marker
        if twitter_follows:
            processed_quests.append("TwitterFollow")
        
        # Get wallets delay settings
        
        # Create tasks for all wallets
        tasks = []
        for i, wallet in enumerate(wallets):
            # Add random delay between wallet processing starts
            
            # Create task for processing wallet
            task = asyncio.create_task(process_wallet_with_specific_quests(wallet, processed_quests, twitter_follows))
            tasks.append(task)
        
        # If no tasks, exit
        if not tasks:
            logger.warning("没有钱包要处理")
            return
            
        # Start all tasks
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Analyze results
        success_count = sum(1 for result in results if result is True)
        error_count = sum(1 for result in results if isinstance(result, Exception) or result is False)
        
        logger.info(f"处理完成: 成功 {success_count}，出错 {error_count}")
        
    except Exception as e:
        logger.error(f"执行所有钱包任务时出错: {str(e)}")

async def get_wallets_stats():
    """Gets statistics for all wallets from database, including Twitter integration"""
    try:
        # Get all wallets from database
        async with Session() as session:
            db = DB(session=session)
            wallets = await db.get_all_wallets()
        
        if not wallets:
            logger.error("没有钱包在数据库中")
            return
        
        logger.info(f"获取 {len(wallets)} 钱包的统计信息")
        
        # Create dictionary for reverse search by ID
        quest_names_by_id = {quest_id: quest_name for quest_name, quest_id in QuestClient.QUEST_IDS.items()}
        
        # Add Twitter tasks to dictionary
        twitter_quests = {}
        for account_name, quest_id in TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {}).items():
            quest_names_by_id[quest_id] = f"Twitter Follow: @{account_name}"
            twitter_quests[quest_id] = account_name
        
        # Get total tasks count (including Twitter)
        total_quests_count = len(QuestClient.QUEST_IDS) + len(twitter_quests)
        
        # Create dictionary to store statistics
        stats = {}
        
        # For each wallet get statistics from database
        for wallet in wallets:
            try:
                # Get completed tasks list
                completed_quests_ids = wallet.completed_quests.split(',') if wallet.completed_quests and wallet.completed_quests != '' else []
                completed_count = len(completed_quests_ids) if completed_quests_ids else 0
                
                # Get completed tasks names by their ID
                completed_quest_names = []
                
                # Regular quests
                regular_completed = 0
                twitter_completed = 0
                
                for quest_id in completed_quests_ids:
                    quest_name = quest_names_by_id.get(quest_id)
                    
                    if quest_name:
                        completed_quest_names.append(quest_name)
                        
                        # Define task type and update counters
                        if quest_id in twitter_quests:
                            twitter_completed += 1
                        else:
                            regular_completed += 1
                    else:
                        completed_quest_names.append(f"Unknown ({quest_id})")
                
                # Add Twitter information
                twitter_status = "Connected" if wallet.twitter_token else "Not connected"
                twitter_health = "OK" if wallet.twitter_status == "OK" else "Problem" if wallet.twitter_status == "BAD" else "Not determined"
                
                stats[wallet.public_key] = {
                    "completed_count": completed_count,
                    "total_count": total_quests_count,
                    "regular_completed": regular_completed,
                    "twitter_completed": twitter_completed,
                    "regular_total": len(QuestClient.QUEST_IDS),
                    "twitter_total": len(twitter_quests),
                    "completed_quests": completed_quest_names,
                    "twitter_status": twitter_status,
                    "twitter_health": twitter_health
                }
                
            except Exception as e:
                stats[wallet.public_key] = {"error": str(e)}
        
        # Output statistics
        print("\n=== 钱包统计 ===")
        
        # Sort wallets by completed tasks count (descending)
        sorted_wallets = sorted(
            stats.keys(), 
            key=lambda k: stats[k].get("completed_count", 0) if "error" not in stats[k] else -1, 
            reverse=True
        )
        
        for wallet_key in sorted_wallets:
            wallet_stats = stats[wallet_key]
            
            if "error" in wallet_stats:
                logger.warning(f"{wallet_key}: {wallet_stats['error']}")
            else:
                percent = int((wallet_stats['completed_count'] / wallet_stats['total_count']) * 100)
                status_color = "green" if percent == 100 else "yellow" if percent > 50 else "red"
                
                # Shorten wallet address for compactness
                short_key = f"{wallet_key[:6]}...{wallet_key[-4:]}"
                
                # Full statistics with breakdown by regular and Twitter tasks
                logger.info(f"{short_key}: {wallet_stats['completed_count']}/{wallet_stats['total_count']} 任务 ({percent}%), " + 
                           f"常规: {wallet_stats['regular_completed']}/{wallet_stats['regular_total']}, " +
                           f"Twitter: {wallet_stats['twitter_completed']}/{wallet_stats['twitter_total']}, " +
                           f"Twitter: {wallet_stats['twitter_status']} ({wallet_stats['twitter_health']})")
                
                # If there are completed tasks, output them list
                # if wallet_stats['completed_count'] > 0 and wallet_stats['completed_count'] < wallet_stats['total_count']:
                #     # Limit displayed tasks to avoid cluttering output
                #     max_display = 10
                #     if len(wallet_stats['completed_quests']) > max_display:
                #         display_quests = wallet_stats['completed_quests'][:max_display]
                #         completed_list = ", ".join(display_quests) + f"... and more {len(wallet_stats['completed_quests']) - max_display}"
                #     else:
                #         completed_list = ", ".join(wallet_stats['completed_quests'])
                #     
                #     logger.info(f"  Completed tasks: {completed_list}")
                
        # Output overall statistics
        total_wallets = len(stats)
        completed_wallets = sum(1 for wallet in stats.values() if "error" not in wallet and wallet["completed_count"] == wallet["total_count"])
        average_completion = sum(wallet["completed_count"] for wallet in stats.values() if "error" not in wallet) / total_wallets if total_wallets > 0 else 0
        
        # Separate statistics for regular and Twitter tasks
        regular_average = sum(wallet["regular_completed"] for wallet in stats.values() if "error" not in wallet) / total_wallets if total_wallets > 0 else 0
        twitter_average = sum(wallet["twitter_completed"] for wallet in stats.values() if "error" not in wallet) / total_wallets if total_wallets > 0 else 0
        
        # Twitter connection statistics
        twitter_connected = sum(1 for wallet in stats.values() if "error" not in wallet and wallet["twitter_status"] == "Connected")
        twitter_healthy = sum(1 for wallet in stats.values() if "error" not in wallet and wallet["twitter_health"] == "OK")
        
        print("\n=== 总体统计 ===")
        print(f"总共钱包: {total_wallets}")
        print(f"完全完成: {completed_wallets} ({int((completed_wallets/total_wallets)*100)}%)")
        print(f"平均完成任务数: {average_completion:.1f} 个")
        print(f"  - 常规任务: {regular_average:.1f} 个")
        print(f"  - Twitter 任务: {twitter_average:.1f} 个")
        print(f"Twitter 状态: 连接 {twitter_connected} 个")
        print(f"Twitter 健康: 正常 {twitter_healthy} 个")
        
        return stats
            
    except Exception as e:
        logger.error(f"获取统计时出错: {str(e)}")
        return {}
