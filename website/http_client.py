from curl_cffi.requests import AsyncSession
from curl_cffi import CurlError
import asyncio
import random
import json
import aiohttp
from typing import Dict, Tuple, Union, Optional
from loguru import logger
from website.captcha_handler import CloudflareHandler
from utils.db_api_async.db_api import Session
from utils.db_api_async.models import User
from data.config import ACTUAL_UA
from data.models import Settings


class BaseHttpClient:
    """基础 HTTP 客户端，用于执行请求"""
        
    def __init__(self, user: User):
        """
        初始化基础 HTTP 客户端
        
        Args:
            user: 包含私钥和代理的用户
        """
        self.user = user
        self.cookies = {}
        # 代理错误计数器
        self.proxy_errors = 0
        # 验证码错误计数器
        self.captcha_errors = 0
        # 自动处理资源错误的设置
        self.settings = Settings()
        self.max_proxy_errors = self.settings.resources_max_failures
        # 初始化 Cloudflare 处理器
        self.cloudflare_handler = CloudflareHandler(self)
        # 最后一次解决验证码的时间
        self.last_captcha_time = None
        # 验证码最大生命周期（20分钟）
        self.captcha_lifetime = 20 * 60
    
    def _is_captcha_expired(self) -> bool:
        """
        检查验证码是否过期
        
        Returns:
            如果验证码已过期或未解决则返回 True
        """
        import time
        
        if not self.last_captcha_time:
            return True
            
        return (time.time() - self.last_captcha_time) > self.captcha_lifetime
    
    def _update_captcha_time(self):
        """更新最后一次解决验证码的时间"""
        import time
        self.last_captcha_time = time.time()
    
    async def handle_captcha_if_needed(self, url: str, response_text: str) -> bool:
        """
        检查是否需要解决验证码，并在需要时解决
        
        Args:
            url: 请求 URL
            response_text: 响应文本
            
        Returns:
            如果验证码成功解决则返回 True
        """
        # 检查 Cloudflare 保护特征
        logger.info(f"{self.user} 检测到 Cloudflare 验证码，开始解决")
        
        # 解决验证码
        success = await self.cloudflare_handler.handle_cloudflare_protection(html=response_text)
        
        if success:
            # 更新最后一次解决验证码的时间
            self._update_captcha_time()
            return True
        else:
            return False
        
    
    async def get_headers(self, additional_headers: Optional[Dict] = None) -> Dict:
        """
        创建请求的基本头信息
        
        Args:
            additional_headers: 额外的头信息
            
        Returns:
            生成的头信息
        """
        base_headers = {
            'User-Agent': ACTUAL_UA,
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': 'https://loyalty.campnetwork.xyz/',
            'DNT': '1',
            'Sec-GPC': '1',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Priority': 'u=4',
        }
        
        if additional_headers:
            base_headers.update(additional_headers)
            
        return base_headers

    async def request(
        self, 
        url: str, 
        method: str, 
        data: Optional[Dict] = None, 
        json_data: Optional[Dict] = None, 
        params: Optional[Dict] = None, 
        headers: Optional[Dict] = None, 
        timeout: int = 30, 
        retries: int = 5,
        extra_cookies: bool = False,
        allow_redirects: bool = True,
        check_cloudflare: bool = True  # 检查 Cloudflare 保护的标志
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        执行 HTTP 请求，自动处理验证码和代理错误
        
        Args:
            url: 请求 URL
            method: 请求方法（GET, POST 等）
            data: 表单数据
            json_data: JSON 数据
            params: URL 参数
            headers: 额外的头信息
            timeout: 请求超时时间（秒）
            retries: 重试次数
            extra_cookies: 是否使用额外的 cookies
            allow_redirects: 是否跟随重定向
            check_cloudflare: 是否检查和处理 Cloudflare 保护
            
        Returns:
            (bool, data): 成功状态和响应数据
        """
        base_headers = await self.get_headers(headers)
        
        # 配置请求参数
        request_kwargs = {
            'url': url,
            'proxy': self.user.proxy,
            'headers': base_headers,
            'cookies': self.cookies,
            'timeout': timeout,
            'allow_redirects': allow_redirects
        }
        if not extra_cookies:
            self.cookies['accountLinkData']= ""
        if not extra_cookies and self.cookies.get('__cf_bm'):
            self.cookies.pop('__cf_bm')
        # 添加可选参数
        if json_data is not None:
            request_kwargs['json'] = json_data
        if data is not None:
            request_kwargs['data'] = data
        if params is not None:
            request_kwargs['params'] = params
        
        proxy_error_occurred = False
        captcha_error_occurred = False
        
        # 执行请求并重试
        for attempt in range(retries):
            try:
                async with AsyncSession(impersonate="chrome") as session:
                    resp = await getattr(session, method.lower())(**request_kwargs)
                    # 保存响应中的 cookies
                    if resp.cookies:
                        for name, cookie in resp.cookies.items():
                            self.cookies[name] = cookie
                    
                    if 300 <= resp.status_code < 400 and not allow_redirects:
                        headers_dict = dict(resp.headers)
                        return False, headers_dict  # 返回头信息而不是响应体
                        
                    # 成功响应
                    if resp.status_code == 200 or resp.status_code == 202:
                        # 请求成功时重置代理错误计数器
                        self.proxy_errors = 0
                        self.captcha_errors = 0
                        try:
                            json_resp = resp.json()
                            return True, json_resp
                        except Exception:
                            return True, resp.text
                        
                    # 获取响应文本进行分析
                    response_text = resp.text
                    
                    # 检查响应中是否存在 Cloudflare 保护
                    if check_cloudflare and (
                        "Just a moment" in response_text 
                    ):
                        logger.warning(f"{self.user} 检测到 Cloudflare 保护，尝试解决验证码...")
                        captcha_error_occurred = True
                        
                        # 解决验证码
                        captcha_solved = await self.handle_captcha_if_needed(url, response_text)
                        
                        if captcha_solved:
                            # 如果验证码成功解决，重试请求
                            continue
                        else:
                            self.captcha_errors += 1
                            if self.captcha_errors >= 3:
                                logger.error(f"{self.user} 无法在 {self.captcha_errors} 次尝试后解决验证码")
                                return False, "CAPTCHA_FAILED"
                                
                            # 在下次尝试前等待
                            await asyncio.sleep(2 ** attempt)
                            continue
                        
                    # 处理错误
                    if 400 <= resp.status_code < 500:
                        logger.warning(f"{self.user} 收到状态码 {resp.status_code} 在请求 {url}")
                        
                        # 检查是否可能是授权问题
                        if resp.status_code == 401 or resp.status_code == 403:
                            if "!DOCTYPE" not in response_text:
                                logger.error(f"{self.user} 授权错误: {response_text}")
                            return False, response_text
                            
                        # 检查是否达到请求限制
                        if resp.status_code == 429:
                            logger.warning(f"{self.user} 达到请求限制 (429)")
                            
                            # 如果不是最后一次尝试，则等待较长的时间并重试
                            if attempt < retries - 1:
                                wait_time = random.uniform(10, 30)  # 10-30秒
                                logger.info(f"{self.user} 等待 {int(wait_time)} 秒，等待下一次尝试")
                                await asyncio.sleep(wait_time)
                                continue
                            
                            # 解析响应，以获取可能的 JSON 消息
                            try:
                                error_json = json.loads(response_text)
                                return False, error_json
                            except:
                                return False, "RATE_LIMIT"
                                
                        # 解析响应，以获取可能的 JSON 消息
                        try:
                            error_json = json.loads(response_text)
                            return False, error_json
                        except:
                            return False, response_text
                            
                    elif 500 <= resp.status_code < 600:
                        logger.warning(f"{self.user} 收到状态码 {resp.status_code}, 重试 {attempt+1}/{retries}")
                        await asyncio.sleep(2 ** attempt)  # 指数退避
                        continue
                        
                    return False, response_text
                    
            except (CurlError) as e:
                logger.warning(f"{self.user} 连接错误在请求 {url}: {str(e)}")
                
                # 增加代理错误计数器
                if "proxy" in str(e).lower() or "connection" in str(e).lower():
                    self.proxy_errors += 1
                    proxy_error_occurred = True
                    
                    # 如果达到错误限制，标记代理为坏的
                    if self.proxy_errors >= self.max_proxy_errors:
                        logger.warning(f"{self.user} 达到代理错误限制 ({self.proxy_errors}/{self.max_proxy_errors}), 标记为 BAD")
                        from resource_manager import ResourceManager
                        resource_manager = ResourceManager()
                        await resource_manager.mark_proxy_as_bad(self.user.id)
                        
                        # 如果启用自动替换，尝试替换代理
                        if self.settings.resources_auto_replace:
                            success, message = await resource_manager.replace_proxy(self.user.id)
                            if success:
                                logger.info(f"{self.user} 代理自动替换: {message}")
                                # 更新当前客户端的代理
                                async with Session() as session:
                                    updated_user = await session.get(User, self.user.id)
                                    if updated_user:
                                        self.user.proxy = updated_user.proxy
                                        # 更新代理在请求参数中
                                        request_kwargs['proxy'] = self.user.proxy
                                        # 重置错误计数器
                                        self.proxy_errors = 0
                            else:
                                logger.error(f"{self.user} 无法替换代理: {message}")
                
                await asyncio.sleep(2 ** attempt)  # 指数退避
                continue
            except Exception as e:
                logger.error(f"{self.user} 意外错误在请求 {url}: {str(e)}")
                return False, str(e)
