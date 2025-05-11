from functions.create_files import create_files
from functions.activity import add_wallets_db, complete_all_wallets_quests, get_wallets_stats
from website.quest_client import QuestClient
import asyncio
import tasks.logo
from utils.db_api_async.db_init import init_db
from loguru import logger

async def option_add_wallets():
    await add_wallets_db()

async def option_complete_all_quests():
    """Выполняет все незавершенные задания для всех кошельков"""
    await complete_all_wallets_quests()

async def option_complete_specific_quests():
    """Выполняет указанные задания для всех кошельков"""
    # Получаем список доступных заданий
    quests = list(QuestClient.QUEST_IDS.keys())
    
    print("Доступные задания:")
    for i, quest_name in enumerate(quests, 1):
        print(f"{i}. {quest_name}")
    
    print("\nВведите номера заданий через запятую (или 'all' для всех):")
    quest_input = input("> ").strip()
    
    if quest_input.lower() == 'all':
        await complete_all_wallets_quests()
    else:
        try:
            # Парсим введенные номера
            quest_numbers = [int(num.strip()) for num in quest_input.split(",") if num.strip()]
            selected_quests = [quests[num-1] for num in quest_numbers if 1 <= num <= len(quests)]
            
            if not selected_quests:
                logger.error("Не выбрано ни одного задания")
                return
                
            logger.info(f"Выбраны задания: {', '.join(selected_quests)}")
            await complete_all_wallets_quests(selected_quests)
            
        except ValueError:
            logger.error("Некорректный ввод. Введите номера через запятую, например: 1,3,5")
        except IndexError:
            logger.error(f"Номер задания должен быть от 1 до {len(quests)}")

async def option_show_stats():
    """Показывает статистику по всем кошелькам"""
    await get_wallets_stats()

async def main():
    create_files()
    await init_db()
    print('''  Select the action:
    1) Import Wallets in DB
    2) Complete All Quests (выполнить все задания)
    3) Complete Specific Quests (выполнить выбранные задания)
    4) Show Stats (показать статистику)
    5) Exit.''')

    try:
        action = int(input('> '))
        if action == 1:
            await option_add_wallets()
        elif action == 2:
            await option_complete_all_quests()
        elif action == 3:
            await option_complete_specific_quests()
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
