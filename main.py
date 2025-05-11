from functions.create_files import create_files
from functions.activity import add_wallets_db, start_register, complete_all_wallets_quests, get_stats
import asyncio
import tasks.logo
from utils.db_api_async.db_init import init_db
from loguru import logger

async def option_add_wallets():
    await add_wallets_db()

async def option_register():
    await start_register()

async def option_complete_all_quests():
    """Выполняет все незавершенные задания для всех кошельков"""
    await complete_all_wallets_quests()

async def option_show_stats():
    """Показывает статистику по всем кошелькам"""
    await get_stats()

async def main():
    create_files()
    await init_db()
    print('''  Select the action:
    1) Import Wallets in DB
    2) Start Register (авторизация кошельков)
    3) Complete All Quests (выполнить все задания)
    4) Show Stats (показать статистику)
    5) Exit.''')

    try:
        action = int(input('> '))
        if action == 1:
            await option_add_wallets()
        elif action == 2:
            await option_register()
        elif action == 3:
            await option_complete_all_quests()
        elif action == 4:
            await option_show_stats()

    except KeyboardInterrupt:
        print()
    except ValueError as err:
        logger.error(f'Value error: {err}')
    except BaseException as e:
        logger.error(f'Something went wrong: {e}')

if __name__ == "__main__":
    asyncio.run(main())
