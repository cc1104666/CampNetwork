import os
from loguru import logger


from libs.eth_async.client import Client
import aiohttp
from libs.eth_async.data.models import Networks
from utils.db_api_async.models import User
from website.website import WebSite

async def handle_register(user: User):
    try:
        client = Client(private_key=user.private_key,
                        network=Networks.Arbitrum,
                        proxy=user.proxy, check_proxy=True)
    except Exception as e:
        print(e)
        logger.error(f'{user} bad proxy')
        return
    logger.info(f'Start working with {user}')
    connector = aiohttp.TCPConnector(limit=10, force_close=False, keepalive_timeout=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        website = WebSite(user=user, client=client, session=session)
        await website.login()
    return
