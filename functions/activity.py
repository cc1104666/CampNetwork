import os
from loguru import logger
import asyncio
from .website_activity import handle_register
from libs.eth_async.client import Client
from libs.eth_async.utils.utils import parse_proxy
from libs.eth_async.data.models import Networks
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config
from data.models import Settings
from fake_useragent import UserAgent

settings = Settings()
private_file = config.PRIVATE_FILE
if os.path.exists(private_file):
    with open(private_file, 'r') as private_file:
        private = [line.strip() for line in private_file if line.strip()]

proxy_file = config.PROXY_FILE
if os.path.exists(proxy_file):
    with open(proxy_file, 'r') as proxy_file:
        proxys = [line.strip() for line in proxy_file if line.strip()]


async def add_wallets_db():
    logger.info(f'Start import wallets')
    for i in range(len(private)):
        random_user_agent = UserAgent(
            os=['windows', 'macos', 'linux'], browsers='chrome')
        user_agent = random_user_agent.random
        private_key = private[i]
        proxy = proxys[i]
        proxy = parse_proxy(proxy)
        client = Client(private_key=private_key,
                        network=Networks.Ethereum)
        async with Session() as session:
            db = DB(session=session)
            await db.add_wallet(private_key=private_key, public_key=client.account.address, proxy=proxy, user_agent=user_agent)

    logger.success('Success import wallets')
    return

async def start_register():
    async with Session() as session:
        db = DB(session=session)
        wallets = await db.get_all_wallets()
    tasks = [handle_register(user=user) for user in wallets]
    task_gathering = asyncio.gather(*tasks)
    await task_gathering
