from functions.create_files import create_files
from functions.activity import (add_wallets_db, complete_all_wallets_quests, 
                               get_wallets_stats, complete_specific_quests,
                               )
from website.quest_client import QuestClient
import asyncio
import tasks.logo
from utils.db_api_async.db_init import init_db
from loguru import logger
from data.models import Settings


async def option_add_wallets():
    await add_wallets_db()

async def option_complete_all_quests():
    """Выполняет все незавершенные задания для всех кошельков"""
    await complete_all_wallets_quests()

async def option_complete_specific_quests():
    """Выполняет указанные задания для всех кошельков"""
    await complete_specific_quests()

async def option_show_stats():
    """Показывает статистику по всем кошелькам"""
    await get_wallets_stats()


async def option_update_settings():
    """Обновляет настройки программы"""
    settings = Settings()
    try:
        # Выводим текущие настройки
        print("\nТекущие настройки:")
        
        # Twitter настройки
        print("\n1. Twitter настройки:")
        print(f"   Использовать Twitter: {'Да' if settings.twitter_enabled else 'Нет'}")
        print(f"   Задержка между действиями в Twitter: {settings.twitter_delay_actions_min}-{settings.twitter_delay_actions_max} секунд")
        print(f"   Задержка между заданиями Twitter: {settings.twitter_delay_quests_min}-{settings.twitter_delay_quests_max} секунд")
        
        # Общие настройки
        print("\n2. Общие настройки:")
        print(f"   Задержка между заданиями: {settings.quest_delay_min}-{settings.quest_delay_max} секунд")
        
        # Настройки кошельков
        print("\n3. Настройки кошельков:")
        wallet_end = "все" if settings.wallet_range_end == 0 else settings.wallet_range_end
        print(f"   Диапазон кошельков: {settings.wallet_range_start}-{wallet_end}")
        print(f"   Задержка между запуском аккаунтов: {settings.wallet_startup_delay_min}-{settings.wallet_startup_delay_max} секунд")
        
        # Запрашиваем, какие настройки обновить
        print("\nВыберите настройки для обновления:")
        print("1. Twitter настройки")
        print("2. Общие настройки")
        print("3. Настройки кошельков")
        print("4. Все настройки")
        print("5. Назад")
        
        choice = int(input("> "))
        
        if choice == 5:
            return
        
        # Получаем текущие настройки из json файла
        from libs.eth_async.utils.files import read_json, write_json
        from data.config import SETTINGS_FILE
        
        current_settings = read_json(path=SETTINGS_FILE)
        
        # Обновляем Twitter настройки
        if choice in [1, 4]:
            print("\nОбновление Twitter настроек:")
            
            # Использовать Twitter
            use_twitter = input("Использовать Twitter (y/n) [текущее: " + 
                             ("y" if settings.twitter_enabled else "n") + "]: ").strip().lower()
            if use_twitter in ["y", "n"]:
                current_settings["twitter"]["enabled"] = (use_twitter == "y")
            
            # Задержка между действиями
            action_delay_min = input(f"Минимальная задержка между действиями (секунды) [текущее: {settings.twitter_delay_actions_min}]: ").strip()
            if action_delay_min.isdigit() and int(action_delay_min) > 0:
                current_settings["twitter"]["delay_between_actions"]["min"] = int(action_delay_min)
                
            action_delay_max = input(f"Максимальная задержка между действиями (секунды) [текущее: {settings.twitter_delay_actions_max}]: ").strip()
            if action_delay_max.isdigit() and int(action_delay_max) > int(current_settings["twitter"]["delay_between_actions"]["min"]):
                current_settings["twitter"]["delay_between_actions"]["max"] = int(action_delay_max)
            
            # Задержка между заданиями
            quest_delay_min = input(f"Минимальная задержка между заданиями Twitter (секунды) [текущее: {settings.twitter_delay_quests_min}]: ").strip()
            if quest_delay_min.isdigit() and int(quest_delay_min) > 0:
                current_settings["twitter"]["delay_between_quests"]["min"] = int(quest_delay_min)
                
            quest_delay_max = input(f"Максимальная задержка между заданиями Twitter (секунды) [текущее: {settings.twitter_delay_quests_max}]: ").strip()
            if quest_delay_max.isdigit() and int(quest_delay_max) > int(current_settings["twitter"]["delay_between_quests"]["min"]):
                current_settings["twitter"]["delay_between_quests"]["max"] = int(quest_delay_max)
        
        # Обновляем общие настройки
        if choice in [2, 4]:
            print("\nОбновление общих настроек:")
            
            # Задержка между заданиями
            quest_delay_min = input(f"Минимальная задержка между заданиями (секунды) [текущее: {settings.quest_delay_min}]: ").strip()
            if quest_delay_min.isdigit() and int(quest_delay_min) > 0:
                current_settings["quests"]["delay_between_quests"]["min"] = int(quest_delay_min)
                
            quest_delay_max = input(f"Максимальная задержка между заданиями (секунды) [текущее: {settings.quest_delay_max}]: ").strip()
            if quest_delay_max.isdigit() and int(quest_delay_max) > int(current_settings["quests"]["delay_between_quests"]["min"]):
                current_settings["quests"]["delay_between_quests"]["max"] = int(quest_delay_max)
        
        # Обновляем настройки кошельков
        if choice in [3, 4]:
            print("\nОбновление настроек кошельков:")
            
            # Диапазон кошельков
            wallet_start = input(f"Начальный индекс кошелька [текущее: {settings.wallet_range_start}]: ").strip()
            if wallet_start.isdigit() and int(wallet_start) >= 0:
                current_settings["wallets"]["range"]["start"] = int(wallet_start)
                
            wallet_end = input(f"Конечный индекс кошелька (0 = все) [текущее: {settings.wallet_range_end}]: ").strip()
            if wallet_end.isdigit() and int(wallet_end) >= 0:
                current_settings["wallets"]["range"]["end"] = int(wallet_end)
            
            # Задержка между запуском аккаунтов
            startup_delay_min = input(f"Минимальная задержка между запуском аккаунтов (секунды) [текущее: {settings.wallet_startup_delay_min}]: ").strip()
            if startup_delay_min.isdigit() and int(startup_delay_min) > 0:
                current_settings["wallets"]["startup_delay"]["min"] = int(startup_delay_min)
                
            startup_delay_max = input(f"Максимальная задержка между запуском аккаунтов (секунды) [текущее: {settings.wallet_startup_delay_max}]: ").strip()
            if startup_delay_max.isdigit() and int(startup_delay_max) > int(current_settings["wallets"]["startup_delay"]["min"]):
                current_settings["wallets"]["startup_delay"]["max"] = int(startup_delay_max)
        
        # Сохраняем обновленные настройки
        write_json(path=SETTINGS_FILE, obj=current_settings, indent=2)
        logger.success("Настройки успешно обновлены")
        
        # Перезагружаем настройки
        settings = Settings()
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении настроек: {str(e)}")

async def main():
    create_files()
    await init_db()
    print('''  Select the action:
    1) Import Wallets in DB
    2) Complete All Quests (выполнить все задания)
    3) Complete Specific Quests (выполнить выбранные задания)
    4) Show Stats (показать статистику)
    5) Settings (настройки)
    6) Exit.''')

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
        elif action == 5:
            await option_update_settings()

    except KeyboardInterrupt:
        print()
    except ValueError as err:
        logger.error(f'Value error: {err}')
    except BaseException as e:
        logger.error(f'Something went wrong: {e}')

if __name__ == "__main__":
    asyncio.run(main())
