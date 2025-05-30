import asyncio
import aiohttp
import json
import base64
import urllib.parse
from typing import Dict, Optional, Tuple, Union
from loguru import logger
from urllib.parse import urlparse
from data.config import CAPMONSTER_API_KEY, ACTUAL_UA


class CloudflareHandler:
    """Cloudflare Turnstile 保护处理器"""
    
    def __init__(self, http_client):
        """
        初始化 Cloudflare 处理器
        
        Args:
            http_client: 用于执行请求的 HTTP 客户端
        """
        self.http_client = http_client
    
    async def parse_proxy(self) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
        """
        解析代理字符串为组件
        
        Returns:
            Tuple[ip, port, login, password]
        """
        if not self.http_client.user.proxy:
            return None, None, None, None
            
        parsed = urlparse(self.http_client.user.proxy)
        
        ip = parsed.hostname
        port = parsed.port
        login = parsed.username
        password = parsed.password
        
        return ip, port, login, password
    
    def encode_html_to_base64(self, html_content: str) -> str:
        """
        将 HTML 编码为 base64
        
        Args:
            html_content: 要编码的 HTML 内容
            
        Returns:
            编码为 base64 的 HTML
        """
        # JavaScript 中 encodeURIComponent 的等效实现
        encoded = urllib.parse.quote(html_content)
        
        # JavaScript 中 unescape 的等效实现（替换 %xx 序列）
        unescaped = urllib.parse.unquote(encoded)
        
        # JavaScript 中 btoa 的等效实现
        base64_encoded = base64.b64encode(unescaped.encode('latin1')).decode('ascii')
        
        return base64_encoded
    
    async def get_recaptcha_task(self, html: str) -> Optional[int]:
        """
        在 CapMonster 中创建 Cloudflare Turnstile 解决任务
        
        Args:
            html: 包含验证码的 HTML 页面
            
        Returns:
            任务 ID 或出错时为 None
        """
        try:
            # 解析代理
            ip, port, login, password = await self.parse_proxy()
            
            # 将 HTML 编码为 base64
            html_base64 = self.encode_html_to_base64(html)           
            windows_user_agent = ACTUAL_UA
            
            # CapMonster 请求数据
            json_data = {
                "clientKey": CAPMONSTER_API_KEY,
                "task": {
                    "type": "TurnstileTask",
                    "websiteURL": "https://loyalty.campnetwork.xyz/home",
                    "websiteKey": "0x4AAAAAAADnPIDROrmt1Wwj",
                    "cloudflareTaskType": "cf_clearance",  # 需要 cf_clearance cookie
                    "htmlPageBase64": html_base64,
                    "userAgent": windows_user_agent
                }
            }
            
            # 如果有代理数据则添加
            if ip and port:
                json_data["task"].update({
                    "proxyType": "http",
                    "proxyAddress": ip,
                    "proxyPort": port
                })
                
                if login and password:
                    json_data["task"].update({
                        "proxyLogin": login,
                        "proxyPassword": password
                    })
                    
            # 创建新会话
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url='https://api.capmonster.cloud/createTask',
                    json=json_data
                ) as resp:
                    if resp.status == 200:
                        result = await resp.text()
                        result = json.loads(result)               
                        if result.get('errorId') == 0:
                            logger.info(f"{self.http_client.user} 已在 CapMonster 创建任务: {result['taskId']}")
                            return result['taskId']
                        else:
                            logger.error(f"{self.http_client.user} CapMonster 错误: {result.get('errorDescription', '未知错误')}")
                            return None
                    else:
                        logger.error(f"{self.http_client.user} CapMonster 请求错误: {resp.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"{self.http_client.user} 创建 CapMonster 任务时出错: {str(e)}")
            return None
    
    async def get_recaptcha_token(self, task_id: int) -> Optional[str]:
        """
        从 CapMonster 获取任务解决结果
        
        Args:
            task_id: 任务 ID
            
        Returns:
            cf_clearance 令牌或出错时为 None
        """
        json_data = {
            "clientKey": CAPMONSTER_API_KEY,
            "taskId": task_id
        }
        
        # 最大等待时间（60秒）
        max_attempts = 60
        
        for i in range(max_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url='https://api.capmonster.cloud/getTaskResult',
                        json=json_data
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.text()
                            result = json.loads(result)                 
                            if result['status'] == 'ready':
                                # 从解决方案中获取 cf_clearance
                                if 'solution' in result:
                                    cf_clearance = result['solution'].get('cf_clearance') or result['solution'].get('token')
                                    logger.success(f"{self.http_client.user} 已获取 cf_clearance 令牌")
                                    return cf_clearance
                                    
                                logger.error(f"{self.http_client.user} 解决方案中不包含 cf_clearance")
                                return None
                                
                            elif result['status'] == 'processing':
                                # 如果任务仍在处理中，等待1秒
                                await asyncio.sleep(1)
                                continue
                            else:
                                logger.error(f"{self.http_client.user} 未知任务状态: {result['status']}")
                                return None
                        else:
                            logger.error(f"{self.http_client.user} 获取结果时出错: {resp.status}")
                            await asyncio.sleep(2)
                            continue
                            
            except Exception as e:
                logger.error(f"{self.http_client.user} 获取结果时出错: {str(e)}")
                return None
                
        logger.error(f"{self.http_client.user} 等待 CapMonster 解决方案超时")
        return None
    
    async def recaptcha_handle(self, html: str) -> Optional[str]:
        """
        通过 CapMonster 处理 Cloudflare Turnstile 验证码
        
        Args:
            html: 包含验证码的 HTML 页面
            
        Returns:
            cf_clearance 令牌或出错时为 None
        """
        max_retry = 10
        captcha_token = None
        
        for i in range(max_retry):
            try:
                # 获取 Turnstile 解决任务
                task = await self.get_recaptcha_task(html=html)
                if not task:
                    logger.error(f"{self.http_client.user} 无法在 CapMonster 创建任务, 尝试 {i+1}/{max_retry}")
                    await asyncio.sleep(2)
                    continue
                
                # 获取解决方案
                result = await self.get_recaptcha_token(task_id=task)
                if result:
                    captcha_token = result
                    logger.success(f"{self.http_client.user} 成功获取验证码")
                    break
                else:
                    logger.warning(f"{self.http_client.user} 无法获取令牌, 尝试 {i+1}/{max_retry}")
                    await asyncio.sleep(3)
                    continue
                    
            except Exception as e:
                logger.error(f"{self.http_client.user} 验证码处理时出错: {str(e)}")
                await asyncio.sleep(3)
                continue
                    
        return captcha_token
    
    async def handle_cloudflare_protection(self, html: str) -> bool:
        """
        处理 Cloudflare 保护
        
        Args:
            html: 包含验证码的 HTML 页面
            
        Returns:
            处理成功状态
        """
        try:
            # 获取验证码令牌
            captcha_token = await self.recaptcha_handle(html=html)
            if not captcha_token:
                logger.error(f"{self.http_client.user} 无法获取验证码令牌")
                return False
            
            # 设置 cf_clearance cookie
            self.http_client.cookies.update({
                'cf_clearance': captcha_token
            })
            
            logger.success(f"{self.http_client.user} 成功处理 Cloudflare 保护")
            return True
            
        except Exception as e:
            logger.error(f"{self.http_client.user} 处理 Cloudflare 保护时出错: {str(e)}")
            return False
