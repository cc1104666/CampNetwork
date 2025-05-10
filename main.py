from functions.create_files import create_files
from functions.activity import add_wallets_db, start_register
import asyncio
import tasks.logo
from utils.db_api_async.db_init import init_db
from loguru import logger

async def option_add_wallets():
    await add_wallets_db()

async def option_register():
    await start_register()

async def main():
    create_files()
    await init_db()
    print('''  Select the action:
    1) Import Wallets in DB
    2) Start Register 
    3) Exit.''')

    try:
        action = int(input('> '))
        if action == 1:
            await option_add_wallets()
        if action == 2:
            await option_register()

    except KeyboardInterrupt:
        print()

    except ValueError as err:
        logger.error(f'Value error: {err}')

    except BaseException as e:
        logger.error(f'Something went wrong: {e}')

if __name__ == "__main__":
    asyncio.run(main())
