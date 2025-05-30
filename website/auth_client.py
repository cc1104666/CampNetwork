import json
import asyncio
import random
from datetime import datetime
from typing import Dict, Optional, Tuple
from loguru import logger
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from eth_account.messages import encode_defunct
from libs.eth_async.client import Client
from .http_client import BaseHttpClient
from .captcha_handler import CloudflareHandler


class AuthClient(BaseHttpClient):
    """CampNetwork 认证客户端"""
    
    # 认证 URL
    BASE_URL = "https://loyalty.campnetwork.xyz"
    AUTH_CSRF_URL = f"{BASE_URL}/api/auth/csrf"
    AUTH_CALLBACK_URL = f"{BASE_URL}/api/auth/callback/credentials"
    AUTH_SESSION_URL = f"{BASE_URL}/api/auth/session"
    AUTH_SIGNOUT_URL = f"{BASE_URL}/api/auth/signout"
    DYNAMIC_CONNECT_URL = "https://app.dynamicauth.com/api/v0/sdk/09a766ae-a662-4d96-904a-28d1c9e4b587/connect"
    DYNAMIC_NONCE_URL = "https://app.dynamicauth.com/api/v0/sdk/09a766ae-a662-4d96-904a-28d1c9e4b587/nonce"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = Client(
            private_key=self.user.private_key,
            proxy=self.user.proxy,
            check_proxy=False
        )
        self.cloudflare = CloudflareHandler(self)
        
        # 认证数据
        self.csrf_token = None
        self.nonce = None
        self.session_data = None
        self.user_id = None
    
    async def initial_request(self) -> bool:
        """
        执行初始请求以检查是否存在 Cloudflare 保护
        
        Returns:
            成功状态
        """
        try:
            logger.info(f"{self.user} 正在执行初始请求以检查 Cloudflare 保护")
            
            # 检查是否存在 Cloudflare 保护
            
            success, response = await self.request(
                url=f"{self.BASE_URL}/home",
                method="GET",
                check_cloudflare=True  # 启用自动检查和处理 Cloudflare
            )
            if success:
                logger.success(f"{self.user} 初始请求成功")
                return True
            else:
                logger.error(f"{self.user} 无法执行初始请求")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 执行初始请求时出错: {str(e)}")
            return False
    
    async def connect_wallet(self) -> bool:
        """
        认证第一阶段 - 通过 Dynamic Auth 连接钱包
        
        Returns:
            成功状态
        """
        json_data = {
            'address': f'{self.user.public_key}',
            'chain': 'EVM',
            'provider': 'browserExtension',
            'walletName': 'rabby',
            'authMode': 'connect-only',
        }
        
        headers = await self.get_headers({
            'Content-Type': 'application/json',
            'x-dyn-version': 'WalletKit/3.9.11',
            'x-dyn-api-version': 'API/0.0.586',
            'Origin': 'https://loyalty.campnetwork.xyz',
        })
        
        success, response = await self.request(
            url=self.DYNAMIC_CONNECT_URL,
            method="POST",
            json_data=json_data,
            headers=headers
        )
        
        if success:
            logger.info(f"{self.user} 成功连接钱包")
            return True
        else:
            logger.error(f"{self.user} 无法连接钱包: {response}")
            return False
    
    async def get_nonce(self) -> bool:
        """
        获取认证所需的 nonce
        
        Returns:
            成功状态
        """
        headers = await self.get_headers({
            'x-dyn-version': 'WalletKit/3.9.11',
            'x-dyn-api-version': 'API/0.0.586',
        })
        
        success, response = await self.request(
            url=self.DYNAMIC_NONCE_URL,
            method="GET",
            headers=headers
        )
        
        if success and isinstance(response, dict) and 'nonce' in response:
            self.nonce = response['nonce']
            logger.info(f"{self.user} 获取到 nonce: {self.nonce[:10]}...")
            return True
        else:
            logger.error(f"{self.user} 无法获取 nonce: {response}")
            return False
    
    async def get_csrf_token(self) -> bool | str:
        """
        获取 CSRF 令牌，检查请求限制
        
        Returns:
            成功状态或错误代码字符串
        """
        headers = await self.get_headers({
            'Content-Type': 'application/json',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Origin': 'https://loyalty.campnetwork.xyz',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        success, response = await self.request(
            url=self.AUTH_CSRF_URL,
            method="GET",
            headers=headers
        )
        
        if success and isinstance(response, dict) and 'csrfToken' in response:
            self.csrf_token = response['csrfToken']
            logger.info(f"{self.user} 获取到 CSRF 令牌: {self.csrf_token[:10]}...")
            return True
        else:
            # 检查是否超过请求限制
            if isinstance(response, dict) and response.get("message") == "Too many requests, please try again later.":
                logger.warning(f"{self.user} 获取 CSRF 令牌时超过请求限制")
                return "RATE_LIMIT"
            else:
                logger.error(f"{self.user} 无法获取 CSRF 令牌: {response}")
                return False

    async def sign_message(self) -> Tuple[Optional[Dict], Optional[str]]:
        """
        签名认证消息
        
        Returns:
            (message, signature): 消息和签名
        """
        if not self.nonce:
            logger.error(f"{self.user} 尝试在没有 nonce 的情况下签名消息")
            return None, None
            
        try:
            # 当前日期和时间，ISO 格式
            current_time = datetime.utcnow().isoformat('T') + 'Z'
            
            # 创建要签名的消息
            message = {
                "domain": "loyalty.campnetwork.xyz",
                "address": self.user.public_key,
                "statement": "Sign in to the app. Powered by Snag Solutions.",
                "uri": "https://loyalty.campnetwork.xyz",
                "version": "1",
                "chainId": 1,
                "nonce": self.nonce,
                "issuedAt": current_time
            }
            
            # 创建 EIP-191 格式的消息字符串
            message_str = (
                f"loyalty.campnetwork.xyz wants you to sign in with your Ethereum account:\n"
                f"{message['address']}\n\n"
                f"{message['statement']}\n\n"
                f"URI: {message['uri']}\n"
                f"Version: {message['version']}\n"
                f"Chain ID: {message['chainId']}\n"
                f"Nonce: {message['nonce']}\n"
                f"Issued At: {message['issuedAt']}"
            )
            
            # 对消息进行编码以进行签名
            message_bytes = encode_defunct(text=message_str)
            
            # 对消息进行签名
            sign = self.client.account.sign_message(message_bytes)
            signature = sign.signature.hex()
            
            logger.info(f"{self.user} 成功签名消息")
            
            return message, signature
            
        except Exception as e:
            logger.error(f"{self.user} 签名消息时出错: {str(e)}")
            return None, None
    
    async def authenticate(self) -> bool:
        """
        执行认证过程
        
        Returns:
            成功状态
        """
        try:
            # 连接钱包
            if not await self.connect_wallet():
                return False
            
            # 获取 nonce
            if not await self.get_nonce():
                return False
            
            # 获取 CSRF 令牌
            csrf_result = await self.get_csrf_token()
            if csrf_result is False:
                return False
            elif csrf_result == "RATE_LIMIT":
                # 如果超过请求限制，等待后重试
                logger.info(f"{self.user} 等待 60 秒后重试...")
                await asyncio.sleep(60)
                csrf_result = await self.get_csrf_token()
                if csrf_result is not True:
                    return False
            
            # 签名消息
            message, signature = await self.sign_message()
            if not message or not signature:
                return False
            
            # 准备认证数据
            json_data = {
                'message': message,
                'signature': signature,
                'redirect': False,
                'csrfToken': self.csrf_token,
                'callbackUrl': '/home',
                'json': True
            }
            
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Referer': 'https://loyalty.campnetwork.xyz/home',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Sec-Fetch-Site': 'same-origin',
            })
            
            # 发送认证请求
            success, response = await self.request(
                url=self.AUTH_CALLBACK_URL,
                method="POST",
                json_data=json_data,
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} 认证成功")
                return True
            else:
                logger.error(f"{self.user} 认证失败: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 认证过程中出错: {str(e)}")
            return False
    
    async def get_session_info(self) -> bool:
        """
        获取会话信息
        
        Returns:
            成功状态
        """
        try:
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Referer': 'https://loyalty.campnetwork.xyz/home',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Sec-Fetch-Site': 'same-origin',
            })
            
            success, response = await self.request(
                url=self.AUTH_SESSION_URL,
                method="GET",
                headers=headers
            )
            
            if success and isinstance(response, dict):
                self.session_data = response
                if 'user' in response and 'id' in response['user']:
                    self.user_id = response['user']['id']
                    logger.info(f"{self.user} 获取到会话信息，用户 ID: {self.user_id}")
                    return True
                else:
                    logger.error(f"{self.user} 会话信息中没有用户 ID")
                    return False
            else:
                logger.error(f"{self.user} 无法获取会话信息: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 获取会话信息时出错: {str(e)}")
            return False
    
    async def login(self) -> bool:
        """
        执行完整的登录流程
        
        Returns:
            成功状态
        """
        try:
            # 执行初始请求
            if not await self.initial_request():
                return False
            
            # 执行认证
            if not await self.authenticate():
                return False
            
            # 获取会话信息
            if not await self.get_session_info():
                return False
            
            logger.success(f"{self.user} 登录成功")
            return True
            
        except Exception as e:
            logger.error(f"{self.user} 登录过程中出错: {str(e)}")
            return False
    
    async def get_referral_code(self) -> str | None:
        """
        获取推荐码
        
        Returns:
            推荐码或 None
        """
        try:
            if not self.user_id:
                logger.error(f"{self.user} 尝试获取推荐码但没有用户 ID")
                return None
            
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Referer': 'https://loyalty.campnetwork.xyz/home',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Sec-Fetch-Site': 'same-origin',
            })
            
            success, response = await self.request(
                url=f"{self.BASE_URL}/api/referral/code",
                method="GET",
                headers=headers
            )
            
            if success and isinstance(response, dict) and 'code' in response:
                code = response['code']
                logger.info(f"{self.user} 获取到推荐码: {code}")
                return code
            else:
                logger.error(f"{self.user} 无法获取推荐码: {response}")
                return None
                
        except Exception as e:
            logger.error(f"{self.user} 获取推荐码时出错: {str(e)}")
            return None
    
    async def login_with_referral(self, referral_code: str | None = None) -> bool:
        """
        使用推荐码登录
        
        Args:
            referral_code: 推荐码（可选）
            
        Returns:
            成功状态
        """
        try:
            # 如果未提供推荐码，尝试获取
            if not referral_code:
                referral_code = await self.get_referral_code()
                if not referral_code:
                    logger.error(f"{self.user} 无法获取推荐码")
                    return False
            
            # 执行登录
            if not await self.login():
                return False
            
            # 使用推荐码
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Referer': 'https://loyalty.campnetwork.xyz/home',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Sec-Fetch-Site': 'same-origin',
            })
            
            json_data = {
                'code': referral_code
            }
            
            success, response = await self.request(
                url=f"{self.BASE_URL}/api/referral/use",
                method="POST",
                json_data=json_data,
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} 成功使用推荐码 {referral_code}")
                return True
            else:
                logger.error(f"{self.user} 使用推荐码失败: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} 使用推荐码登录时出错: {str(e)}")
            return False
