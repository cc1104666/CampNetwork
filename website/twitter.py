import asyncio
import random
from typing import Dict, List, Optional, Union, Any, Tuple, Tuple, Tuple, Tuple
from loguru import logger
import twitter  # Import tweepy-self library
from twitter.utils import remove_at_sign
from utils.db_api_async.models import User
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from website.resource_manager import ResourceManager
from website.http_client import BaseHttpClient
from data.config import CAPMONSTER_API_KEY, ACTUAL_UA
from data.models import Settings


class TwitterClient(BaseHttpClient):
    """Twitter API 交互客户端"""

    # 请求 URL
    BASE_URL = "https://loyalty.campnetwork.xyz"
    TWITTER_CONNECT_URL = f"{BASE_URL}/api/loyalty/social/connect/twitter"
    TWITTER_VERIFY_URL = f"{BASE_URL}/api/loyalty/social/verify/twitter"

    # Twitter 账号到任务 ID 的映射
    TWITTER_QUESTS_MAP = {
        "Follow": {
            "StoryChain_ai": "4cebe3ff-4dae-4858-9323-8b669d80e45c",
            "tokentails": "cf5a23b1-d48c-4ab9-a74c-785394158224",
            "PanenkaFC90": "040ead29-7436-4457-b7cd-8bd2a8855a49",
            "ScorePlay_xyz": "5f03c7d8-8ee0-443f-a0ad-8fda68dfecd8",
            "wideworlds_ai": "42936f26-3ec6-401f-8ed0-62af343f1fc4",
            "pets_ww": "242ab4dc-2df4-4b97-bcd7-b013ff6635a1",
            "chronicle_ww": "e47be0b8-eedc-445e-a53e-b2f05daabe3c",
            "PictographsNFT": "4e467350-a49b-4413-8fce-4d424d3303bb",
            "entertainm_io": "beb6df6d-b225-46e5-8a4f-20ad967fb4a8",
            "bleetz_io": "01bc9433-359f-4403-9bc8-4295d47dc3c8",
            "RewardedTV_": "87c040a3-060a-4000-b271-051603417e8b",
            "Fantasy_cristal": "17681189-fd69-4aa3-b533-8f452c1bab0c",
            "belgranofantasy": "1cdb82f7-7878-46fc-baec-b75d6e414a25",
            "awanalab": "1a81cbe5-a792-4921-baa0-0c36165e0d7c",
            "arcoin_official": "b852ec9b-7af5-4f07-a677-1bc630bf4579",
            "TheMetakraft": "39b41034-ce80-4057-8cca-e95992182f04",
            "summitx_finance": "12b177a5-aa4e-47c6-aaa9-b14bf9481d0a",
            "thepixudi": "009c0d38-dc3c-4d37-b558-38ece673724a",
            "clustersxyz": "c7d0e2c8-87e7-46df-81f3-48f311735c22",
            "JukebloxDapp": "02e3d5b3-e65e-41c8-b159-405f48255cdf",
            "campnetworkxyz": "2660f24a-e3ac-4093-8c16-7ae718c00731",
            "hitmakrr": "dfa110a8-4079-4309-a023-e0c9077ace5e",
        }
    }

    def __init__(self, user: User, auth_client, twitter_auth_token: str, twitter_username: str | None = None, 
                 twitter_password: str | None = None, totp_secret: str | None = None):
        """
        初始化 Twitter 客户端
        
        Args:
            user: 用户对象
            auth_client: CampNetwork 的授权客户端
            twitter_auth_token: Twitter 授权令牌
            twitter_username: Twitter 用户名（不带 @）
            twitter_password: Twitter 账号密码
            totp_secret: TOTP 密钥（如果启用了 2FA）
        """
        super().__init__(user=user)
        
        # 保存 auth_client 用于 CampNetwork 请求
        self.auth_client = auth_client
        
        # 创建 Twitter 账号
        self.twitter_account = twitter.Account(
            auth_token=twitter_auth_token,
            username=twitter_username,
            password=twitter_password,
            totp_secret=totp_secret
        )
        
        # Twitter 客户端配置
        self.client_config = {
            "wait_on_rate_limit": True,
            "auto_relogin": True,
            "update_account_info_on_startup": True,
            "capsolver_api_key": CAPMONSTER_API_KEY,
        }
        
        # 如果指定了代理则添加
        if user.proxy:
            self.client_config["proxy"] = user.proxy
            
        # 初始化客户端为 None
        self.twitter_client = None
        self.is_connected = False
        
        # 添加错误跟踪字段
        self.last_error = None
        self.error_count = 0
        self.settings = Settings()

    
    async def initialize(self) -> bool:
        """
        初始化 Twitter 客户端
        
        Returns:
            成功状态
        """
        try:
            # 创建 Twitter 客户端
            self.twitter_client = twitter.Client(self.twitter_account, **self.client_config)
            
            # 建立连接
            await self.twitter_client.__aenter__()
            
            # 检查账号状态
            await self.twitter_client.establish_status()
            
            if self.twitter_account.status == twitter.AccountStatus.GOOD:
                logger.success(f"{self.user} Twitter 客户端已初始化")
                return True
            else:
                error_msg = f"Twitter 账号状态问题: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                self.last_error = error_msg
                self.error_count += 1
                
                # 如果是授权问题，将令牌标记为不良
                if self.twitter_account.status in [twitter.AccountStatus.BAD_TOKEN, twitter.AccountStatus.SUSPENDED]:
                    resource_manager = ResourceManager()
                    await resource_manager.mark_twitter_as_bad(self.user.id)
                    
                    # 如果启用了自动替换，尝试替换令牌
                    auto_replace, _ = self.settings.get_resource_settings()
                    if auto_replace:
                        success, message = await resource_manager.replace_twitter(self.user.id)
                        if success:
                            logger.info(f"{self.user} Twitter 令牌已自动替换: {message}")
                            # 尝试使用新令牌（在另一个方法中）
                
                return False
                
        except Exception as e:
            error_msg = f"初始化 Twitter 客户端时出错: {str(e)}"
            logger.error(f"{self.user} {error_msg}")
            self.last_error = error_msg
            self.error_count += 1
            
            # 检查错误是否表明授权问题
            # if any(x in str(e).lower() for x in ["unauthorized", "authentication", "token", "login", "banned"]):
            resource_manager = ResourceManager()
            await resource_manager.mark_twitter_as_bad(self.user.id)
            
            # 如果启用了自动替换，尝试替换令牌
            auto_replace, _ = self.settings.get_resource_settings()
            if auto_replace:
                success, message = await resource_manager.replace_twitter(self.user.id)
                if success:
                    logger.info(f"{self.user} Twitter 令牌已自动替换: {message}")
                        # 尝试使用新令牌（在另一个方法中）
                
            return False

    async def close(self):
        """关闭 Twitter 连接"""
        if self.twitter_client:
            try:
                await self.twitter_client.__aexit__(None, None, None)
                self.twitter_client = None
                logger.info(f"{self.user} Twitter 客户端已关闭")
            except Exception as e:
                logger.error(f"{self.user} 关闭 Twitter 客户端时出错: {str(e)}")
    
    async def __aenter__(self):
        """上下文管理器入口"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        await self.close()
    
    async def connect_twitter_to_camp(self) -> bool:
        """
        使用现有的 auth_client 将 Twitter 连接到 CampNetwork
        
        Returns:
            成功状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下连接 Twitter")
            return False
            
        try:
            # 检查是否有 auth_client 且用户已授权
            if not hasattr(self, 'auth_client') or not self.auth_client.user_id:
                logger.error(f"{self.user} 缺少 auth_client 或用户未授权")
                return False
            
            # 步骤 1: 请求 /api/twitter/auth 获取 Twitter 授权参数
            logger.info(f"{self.user} 正在请求 Twitter 授权参数")
            
            headers = await self.auth_client.get_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://loyalty.campnetwork.xyz/home',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Priority': 'u=0, i',
            })
            
            # 使用 auth_client 进行请求，但不跟随重定向
            auth_success, auth_response = await self.auth_client.request(
                url="https://loyalty.campnetwork.xyz/api/twitter/auth",
                method="GET",
                headers=headers,
                allow_redirects=False
            )
            
            # 检查是否收到重定向响应
            if 'location' in auth_response:
                # 从 Location header 提取 URL
                twitter_auth_url = auth_response['location']
                
                # 解析 URL 以提取参数
                import urllib.parse
                parsed_url = urllib.parse.urlparse(twitter_auth_url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                # 提取必要的参数
                state = query_params.get('state', [''])[0]
                code_challenge = query_params.get('code_challenge', [''])[0]
                client_id = query_params.get('client_id', ['TVBRYlFuNzg5RVo4QU11b3EzVV86MTpjaQ'])[0]
                redirect_uri = query_params.get('redirect_uri', ['https://snag-render.com/api/twitter/auth/callback'])[0]
                
                if not state or not code_challenge:
                    logger.error(f"{self.user} 无法从授权 URL 提取参数")
                    return False
                
                # 步骤 2: 使用参数进行 OAuth2 授权
                oauth2_data = {
                    'response_type': 'code',
                    'client_id': client_id,
                    'redirect_uri': redirect_uri,
                    'scope': 'users.read tweet.read',
                    'state': state,
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'plain'
                }
                
                # 执行 OAuth2 授权
                auth_code = await self.twitter_client.oauth2(**oauth2_data)
                
                if not auth_code:
                    logger.error(f"{self.user} 无法从 Twitter 获取授权码")
                    return False
                
                # 步骤 3: 请求 callback URL
                callback_url = f"{redirect_uri}?state={state}&code={auth_code}"
                
                callback_headers = {
                    'User-Agent': ACTUAL_UA,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer': 'https://x.com/',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'cross-site',
                }
                
                # 使用 BaseHttpClient 的 request 方法进行请求
                callback_success, callback_response = await self.auth_client.request(
                    url=callback_url,
                    method="GET",
                    headers=callback_headers,
                    allow_redirects=False,
                )
                
                # 检查是否收到重定向到 connect URL
                if not callback_success and isinstance(callback_response, dict) and 'location' in callback_response:
                    connect_url = callback_response['location']
                    
                    # 步骤 4: 执行连接 Twitter
                    connect_headers = await self.auth_client.get_headers({
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Referer': 'https://x.com/',
                        'DNT': '1',
                        'Sec-GPC': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'cross-site',
                        'Sec-Fetch-User': '?1',
                        'Priority': 'u=0, i',
                    })
                    
                    # 使用 auth_client.request 进行请求
                    connect_success, connect_response = await self.auth_client.request(
                        url=connect_url,
                        method="GET",
                        headers=connect_headers,
                        allow_redirects=False
                    )
                    
                    # 检查连接结果
                    if connect_success:
                        logger.success(f"{self.user} Twitter 已连接")
                        self.is_connected = True
                        return True
                    else:
                        # 检查是否收到重定向到主页面
                        if isinstance(connect_response, dict) and 'location' in connect_response and 'loyalty.campnetwork.xyz/loyalty' in connect_response['location']:
                            logger.success(f"{self.user} Twitter 已连接（通过重定向）")
                            self.is_connected = True
                            return True
                        
                        logger.success(f"{self.user} Twitter 已连接")
                        self.is_connected = True
                        return True
                else:
                    logger.error(f"{self.user} 未收到预期的重定向回调 URL")
                    return False
            else:
                logger.error(f"{self.user} 无法从 Twitter 获取重定向到授权")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 连接 Twitter 时出错: {str(e)}")
            return False

    async def disconnect_twitter(self) -> bool:
        """
        从 CampNetwork 断开 Twitter 连接
        
        Returns:
            成功状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下断开 Twitter 连接")
            return False
            
        try:
            # 检查是否有 auth_client 且用户已授权
            if not hasattr(self, 'auth_client') or not self.auth_client.user_id:
                logger.error(f"{self.user} 缺少 auth_client 或用户未授权")
                return False
            
            # 请求断开连接
            headers = await self.auth_client.get_headers({
                'Content-Type': 'application/json',
                'Referer': 'https://loyalty.campnetwork.xyz/loyalty',
                'Origin': 'https://loyalty.campnetwork.xyz',
            })
            
            success, response = await self.auth_client.request(
                url=self.TWITTER_VERIFY_URL,
                method="POST",
                json_data={},
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} Twitter 已断开连接")
                self.is_connected = False
                return True
            else:
                logger.error(f"{self.user} 断开 Twitter 连接时出错: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 断开 Twitter 连接时出错: {str(e)}")
            return False

    async def replace_twitter_token(self, new_token: str) -> bool:
        """
        替换 Twitter 令牌
        
        Args:
            new_token: 新的 Twitter 令牌
            
        Returns:
            成功状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下替换 Twitter 令牌")
            return False
            
        try:
            # 检查是否有 auth_client 且用户已授权
            if not hasattr(self, 'auth_client') or not self.auth_client.user_id:
                logger.error(f"{self.user} 缺少 auth_client 或用户未授权")
                return False
            
            # 创建新的 Twitter 账号
            new_account = twitter.Account(
                auth_token=new_token,
                username=self.twitter_account.username,
                password=self.twitter_account.password,
                totp_secret=self.twitter_account.totp_secret
            )
            
            # 创建新的 Twitter 客户端
            new_client = twitter.Client(new_account, **self.client_config)
            
            # 建立连接
            await new_client.__aenter__()
            
            # 检查账号状态
            await new_client.establish_status()
            
            if new_account.status == twitter.AccountStatus.GOOD:
                # 关闭旧客户端
                await self.close()
                
                # 更新客户端
                self.twitter_account = new_account
                self.twitter_client = new_client
                
                logger.success(f"{self.user} Twitter 令牌已替换")
                return True
            else:
                error_msg = f"新 Twitter 账号状态问题: {new_account.status}"
                logger.error(f"{self.user} {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 替换 Twitter 令牌时出错: {str(e)}")
            return False

    async def check_twitter_connection_status(self) -> bool:
        """
        检查 Twitter 连接状态
        
        Returns:
            连接状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下检查 Twitter 连接状态")
            return False
            
        try:
            # 检查是否有 auth_client 且用户已授权
            if not hasattr(self, 'auth_client') or not self.auth_client.user_id:
                logger.error(f"{self.user} 缺少 auth_client 或用户未授权")
                return False
            
            # 请求验证状态
            headers = await self.auth_client.get_headers({
                'Content-Type': 'application/json',
                'Referer': 'https://loyalty.campnetwork.xyz/loyalty',
                'Origin': 'https://loyalty.campnetwork.xyz',
            })
            
            success, response = await self.auth_client.request(
                url=self.TWITTER_VERIFY_URL,
                method="GET",
                headers=headers
            )
            
            if success and isinstance(response, dict):
                # 检查连接状态
                if response.get('connected', False):
                    logger.success(f"{self.user} Twitter 已连接")
                    self.is_connected = True
                    return True
                else:
                    logger.info(f"{self.user} Twitter 未连接")
                    self.is_connected = False
                    return False
            else:
                logger.error(f"{self.user} 检查 Twitter 连接状态时出错: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 检查 Twitter 连接状态时出错: {str(e)}")
            return False

    async def follow_account(self, account_name: str) -> Tuple[bool, Optional[str], bool]:
        """
        关注 Twitter 账号
        
        Args:
            account_name: 要关注的账号名称
            
        Returns:
            (成功状态, 错误消息, 是否已关注)
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下关注账号")
            return False, "Twitter 客户端未初始化", False
            
        try:
            # 检查账号状态
            if self.twitter_account.status != twitter.AccountStatus.GOOD:
                error_msg = f"Twitter 账号状态问题: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                return False, error_msg, False
            
            # 获取用户 ID
            user_id = await self.twitter_client.get_user_id(account_name)
            
            if not user_id:
                error_msg = f"无法获取用户 ID: {account_name}"
                logger.error(f"{self.user} {error_msg}")
                return False, error_msg, False
            
            # 检查是否已关注
            is_following = await self._check_if_following(user_id)
            
            if is_following:
                logger.info(f"{self.user} 已经关注了 {account_name}")
                return True, None, True
            
            # 关注账号
            success = await self.twitter_client.follow(user_id)
            
            if success:
                logger.success(f"{self.user} 已关注 {account_name}")
                return True, None, False
            else:
                error_msg = f"关注 {account_name} 失败"
                logger.error(f"{self.user} {error_msg}")
                return False, error_msg, False
                
        except Exception as e:
            error_msg = f"关注账号时出错: {str(e)}"
            logger.error(f"{self.user} {error_msg}")
            return False, error_msg, False

    async def _check_if_following(self, user_id: int) -> bool:
        """
        检查是否已关注用户
        
        Args:
            user_id: 用户 ID
            
        Returns:
            是否已关注
        """
        try:
            # 获取关注状态
            following = await self.twitter_client.get_following(user_id)
            
            if following:
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 检查关注状态时出错: {str(e)}")
            return False

    async def post_tweet(self, text: str) -> Optional[Any]:
        """
        发布推文
        
        Args:
            text: 推文内容
            
        Returns:
            推文 ID 或出错时为 None
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下发布推文")
            return None
            
        try:
            # 检查账号状态
            if self.twitter_account.status != twitter.AccountStatus.GOOD:
                error_msg = f"Twitter 账号状态问题: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                return None
            
            # 发布推文
            tweet_id = await self.twitter_client.tweet(text)
            
            if tweet_id:
                logger.success(f"{self.user} 已发布推文: {tweet_id}")
                return tweet_id
            else:
                logger.error(f"{self.user} 发布推文失败")
                return None
                
        except Exception as e:
            logger.error(f"{self.user} 发布推文时出错: {str(e)}")
            return None
    
    async def retweet(self, tweet_id: int) -> bool:
        """
        转发推文
        
        Args:
            tweet_id: 要转发的推文 ID
            
        Returns:
            成功状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下转发推文")
            return False
            
        try:
            # 检查账号状态
            if self.twitter_account.status != twitter.AccountStatus.GOOD:
                error_msg = f"Twitter 账号状态问题: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                return False
            
            # 转发推文
            success = await self.twitter_client.retweet(tweet_id)
            
            if success:
                logger.success(f"{self.user} 已转发推文: {tweet_id}")
                return True
            else:
                logger.error(f"{self.user} 转发推文失败: {tweet_id}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 转发推文时出错: {str(e)}")
            return False
    
    async def like_tweet(self, tweet_id: int) -> bool:
        """
        点赞推文
        
        Args:
            tweet_id: 要点赞的推文 ID
            
        Returns:
            成功状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下点赞推文")
            return False
            
        try:
            # 检查账号状态
            if self.twitter_account.status != twitter.AccountStatus.GOOD:
                error_msg = f"Twitter 账号状态问题: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                return False
            
            # 点赞推文
            success = await self.twitter_client.like(tweet_id)
            
            if success:
                logger.success(f"{self.user} 已点赞推文: {tweet_id}")
                return True
            else:
                logger.error(f"{self.user} 点赞推文失败: {tweet_id}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 点赞推文时出错: {str(e)}")
            return False
    
    async def complete_follow_quest(self, account_name: str) -> bool:
        """
        完成关注任务
        
        Args:
            account_name: 要关注的账号名称
            
        Returns:
            成功状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下完成关注任务")
            return False
            
        try:
            # 检查账号状态
            if self.twitter_account.status != twitter.AccountStatus.GOOD:
                error_msg = f"Twitter 账号状态问题: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                return False
            
            # 获取任务 ID
            quest_id = self.TWITTER_QUESTS_MAP["Follow"].get(account_name)
            
            if not quest_id:
                error_msg = f"未找到任务 ID: {account_name}"
                logger.error(f"{self.user} {error_msg}")
                return False
            
            # 关注账号
            success, error_msg, is_following = await self.follow_account(account_name)
            
            if not success:
                logger.error(f"{self.user} {error_msg}")
                return False
            
            if is_following:
                logger.info(f"{self.user} 已经关注了 {account_name}")
                return True
            
            # 等待一段时间以确保关注状态更新
            await asyncio.sleep(5)
            
            # 验证关注状态
            user_id = await self.twitter_client.get_user_id(account_name)
            
            if not user_id:
                error_msg = f"无法获取用户 ID: {account_name}"
                logger.error(f"{self.user} {error_msg}")
                return False
            
            is_following = await self._check_if_following(user_id)
            
            if not is_following:
                error_msg = f"关注 {account_name} 失败"
                logger.error(f"{self.user} {error_msg}")
                return False
            
            # 完成任务
            headers = await self.auth_client.get_headers({
                'Content-Type': 'application/json',
                'Referer': 'https://loyalty.campnetwork.xyz/loyalty',
                'Origin': 'https://loyalty.campnetwork.xyz',
            })
            
            success, response = await self.auth_client.request(
                url=f"{self.BASE_URL}/api/loyalty/quests/{quest_id}/complete",
                method="POST",
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} 已完成关注任务: {account_name}")
                return True
            else:
                logger.error(f"{self.user} 完成关注任务失败: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 完成关注任务时出错: {str(e)}")
            return False

    async def complete_follow_quests(self, account_names: List[str]) -> Dict[str, bool]:
        """
        完成多个关注任务
        
        Args:
            account_names: 要关注的账号名称列表
            
        Returns:
            任务完成状态
        """
        results = {}
        
        for account_name in account_names:
            success = await self.complete_follow_quest(account_name)
            results[account_name] = success
            
            # 等待一段时间以避免请求限制
            await asyncio.sleep(random.uniform(2, 5))
            
        return results

    async def complete_twitter_quests(self, follow_accounts: List[str] | None = None,
                                     tweet_text: str | None = None,
                                     tweet_id_to_like: int | None = None,
                                     tweet_id_to_retweet: int | None = None) -> bool:
        """
        完成 Twitter 任务
        
        Args:
            follow_accounts: 要关注的账号列表
            tweet_text: 要发布的推文内容
            tweet_id_to_like: 要点赞的推文 ID
            tweet_id_to_retweet: 要转发的推文 ID
            
        Returns:
            成功状态
        """
        if not self.twitter_client:
            logger.error(f"{self.user} 尝试在未初始化客户端的情况下完成 Twitter 任务")
            return False
            
        try:
            # 检查账号状态
            if self.twitter_account.status != twitter.AccountStatus.GOOD:
                error_msg = f"Twitter 账号状态问题: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                return False
            
            # 完成关注任务
            if follow_accounts:
                follow_results = await self.complete_follow_quests(follow_accounts)
                
                if not all(follow_results.values()):
                    logger.error(f"{self.user} 部分关注任务失败")
                    return False
            
            # 发布推文
            if tweet_text:
                tweet_id = await self.post_tweet(tweet_text)
                
                if not tweet_id:
                    logger.error(f"{self.user} 发布推文失败")
                    return False
            
            # 点赞推文
            if tweet_id_to_like:
                success = await self.like_tweet(tweet_id_to_like)
                
                if not success:
                    logger.error(f"{self.user} 点赞推文失败")
                    return False
            
            # 转发推文
            if tweet_id_to_retweet:
                success = await self.retweet(tweet_id_to_retweet)
                
                if not success:
                    logger.error(f"{self.user} 转发推文失败")
                    return False
            
            logger.success(f"{self.user} 已完成所有 Twitter 任务")
            return True
                
        except Exception as e:
            logger.error(f"{self.user} 完成 Twitter 任务时出错: {str(e)}")
            return False
