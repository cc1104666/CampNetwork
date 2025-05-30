from pathlib import Path
from functions.create_files import create_files
from functions.activity import (add_wallets_db, complete_all_wallets_quests, 
                               get_wallets_stats, complete_specific_quests)

from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from website.referral_manager import (
    load_ref_codes, 
    add_ref_code_to_file, 
    update_ref_codes_file_from_db
)

from sqlalchemy import text
from website.resource_manager import ResourceManager
import asyncio
import os
import sys
from loguru import logger
from data.models import Settings
from data import config
import rich
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Создаем консоль для красивого вывода
console = Console()

def print_logo():
    """显示程序标志"""
    # 创建一个更简单的固定宽度边框
    panel = Panel(
        "[bold white]CAMP NETWORK 任务农场[/bold white]\n\n"
        "GitHub: [link]https://github.com/cc1104666/CampNetwork[/link]\n"
        "频道: [link]https://discord.gg/xpjFpug7[/link]",
        width=60,
        border_style="cyan",
        padding=(1, 2)
    )
    console.print(panel)
    console.print()

async def option_update_settings():
    """更新程序设置"""
    settings = Settings()
    try:
        # 显示当前设置
        console.print("\n[bold cyan]当前设置:[/]")
        
        # Twitter 设置
        console.print("\n[bold]1. Twitter 设置:[/]")
        console.print(f"   使用 Twitter: {'[green]是[/]' if settings.twitter_enabled else '[red]否[/]'}")
        console.print(f"   Twitter 操作之间的延迟: {settings.twitter_delay_actions_min}-{settings.twitter_delay_actions_max} 秒")
        console.print(f"   Twitter 任务之间的延迟: {settings.twitter_delay_quests_min}-{settings.twitter_delay_quests_max} 秒")
        
        # 常规设置
        console.print("\n[bold]2. 常规设置:[/]")
        console.print(f"   任务之间的延迟: {settings.quest_delay_min}-{settings.quest_delay_max} 秒")
        
        # 钱包设置
        console.print("\n[bold]3. 钱包设置:[/]")
        wallet_end = "[green]全部[/]" if settings.wallet_range_end == 0 else str(settings.wallet_range_end)
        console.print(f"   钱包范围: {settings.wallet_range_start}-{wallet_end}")
        console.print(f"   账户启动之间的延迟: {settings.wallet_startup_delay_min}-{settings.wallet_startup_delay_max} 秒")
        
        # 资源设置
        console.print("\n[bold]4. 资源设置:[/]")
        console.print(f"   自动替换资源: {'[green]是[/]' if settings.resources_auto_replace else '[red]否[/]'}")
        console.print(f"   最大错误次数: {settings.resources_max_failures}")

        console.print("\n[bold]5. 推荐码设置:[/]")
        console.print(f"   使用数据库中的随机码: {'[green]是[/]' if settings.referrals_use_random_from_db else '[red]否[/]'}")
        console.print(f"   仅使用文件中的码: {'[green]是[/]' if settings.referrals_use_only_file_codes else '[red]否[/]'}")
        
        # 询问要更新哪些设置
        console.print("\n[bold cyan]选择要更新的设置:[/]")
        console.print("1. Twitter 设置")
        console.print("2. 常规设置")
        console.print("3. 钱包设置")
        console.print("4. 资源设置")
        console.print("5. 推荐码设置")
        console.print("6. 所有设置")
        console.print("7. 返回")
        
        choice = int(input("> "))
        
        if choice == 7:
            return
        
        # 从 json 文件获取当前设置
        from libs.eth_async.utils.files import read_json, write_json
        from data.config import SETTINGS_FILE
        
        current_settings = read_json(path=SETTINGS_FILE)
        
        # 更新 Twitter 设置
        if choice in [1, 5]:
            console.print("\n[bold]更新 Twitter 设置:[/]")
            
            # 使用 Twitter
            use_twitter = input("使用 Twitter (y/n) [当前: " + 
                             ("y" if settings.twitter_enabled else "n") + "]: ").strip().lower()
            if use_twitter in ["y", "n"]:
                current_settings["twitter"]["enabled"] = (use_twitter == "y")
            
            # 操作之间的延迟
            action_delay_min = input(f"操作之间的最小延迟（秒）[当前: {settings.twitter_delay_actions_min}]: ").strip()
            if action_delay_min.isdigit() and int(action_delay_min) > 0:
                current_settings["twitter"]["delay_between_actions"]["min"] = int(action_delay_min)
                
            action_delay_max = input(f"操作之间的最大延迟（秒）[当前: {settings.twitter_delay_actions_max}]: ").strip()
            if action_delay_max.isdigit() and int(action_delay_max) > int(current_settings["twitter"]["delay_between_actions"]["min"]):
                current_settings["twitter"]["delay_between_actions"]["max"] = int(action_delay_max)
            
            # 任务之间的延迟
            quest_delay_min = input(f"Twitter 任务之间的最小延迟（秒）[当前: {settings.twitter_delay_quests_min}]: ").strip()
            if quest_delay_min.isdigit() and int(quest_delay_min) > 0:
                current_settings["twitter"]["delay_between_quests"]["min"] = int(quest_delay_min)
                
            quest_delay_max = input(f"Twitter 任务之间的最大延迟（秒）[当前: {settings.twitter_delay_quests_max}]: ").strip()
            if quest_delay_max.isdigit() and int(quest_delay_max) > int(current_settings["twitter"]["delay_between_quests"]["min"]):
                current_settings["twitter"]["delay_between_quests"]["max"] = int(quest_delay_max)
        
        # 更新常规设置
        if choice in [2, 5]:
            console.print("\n[bold]更新常规设置:[/]")
            
            # 任务之间的延迟
            quest_delay_min = input(f"任务之间的最小延迟（秒）[当前: {settings.quest_delay_min}]: ").strip()
            if quest_delay_min.isdigit() and int(quest_delay_min) > 0:
                current_settings["quests"]["delay_between_quests"]["min"] = int(quest_delay_min)
                
            quest_delay_max = input(f"任务之间的最大延迟（秒）[当前: {settings.quest_delay_max}]: ").strip()
            if quest_delay_max.isdigit() and int(quest_delay_max) > int(current_settings["quests"]["delay_between_quests"]["min"]):
                current_settings["quests"]["delay_between_quests"]["max"] = int(quest_delay_max)
        
        # 更新钱包设置
        if choice in [3, 5]:
            console.print("\n[bold]更新钱包设置:[/]")
            
            # 钱包范围
            wallet_start = input(f"起始钱包索引 [当前: {settings.wallet_range_start}]: ").strip()
            if wallet_start.isdigit() and int(wallet_start) >= 0:
                current_settings["wallets"]["range"]["start"] = int(wallet_start)
                
            wallet_end = input(f"结束钱包索引 (0 = 全部) [当前: {settings.wallet_range_end}]: ").strip()
            if wallet_end.isdigit() and int(wallet_end) >= 0:
                current_settings["wallets"]["range"]["end"] = int(wallet_end)
            
            # 账户启动之间的延迟
            startup_delay_min = input(f"账户启动之间的最小延迟（秒）[当前: {settings.wallet_startup_delay_min}]: ").strip()
            if startup_delay_min.isdigit() and int(startup_delay_min) >= 0:
                current_settings["wallets"]["startup_delay"]["min"] = int(startup_delay_min)
                
            startup_delay_max = input(f"账户启动之间的最大延迟（秒）[当前: {settings.wallet_startup_delay_max}]: ").strip()
            if startup_delay_max.isdigit() and int(startup_delay_max) > int(current_settings["wallets"]["startup_delay"]["min"]):
                current_settings["wallets"]["startup_delay"]["max"] = int(startup_delay_max)
        
        # 更新资源设置
        if choice in [4, 5]:
            console.print("\n[bold]更新资源设置:[/]")
            
            # 创建资源部分（如果还没有）
            if "resources" not in current_settings:
                current_settings["resources"] = {
                    "auto_replace": True,
                    "max_failures": 3
                }
            
            # 自动替换
            auto_replace = input(f"自动替换资源 (y/n) [当前: {'y' if settings.resources_auto_replace else 'n'}]: ").strip().lower()
            if auto_replace in ["y", "n"]:
                current_settings["resources"]["auto_replace"] = (auto_replace == "y")
            
            # 最大错误次数
            max_failures = input(f"最大错误次数 [当前: {settings.resources_max_failures}]: ").strip()
            if max_failures.isdigit() and int(max_failures) > 0:
                current_settings["resources"]["max_failures"] = int(max_failures)

        if choice in [5, 6]:
            console.print("\n[bold]更新推荐码设置:[/]")
            
            # 使用数据库中的随机码
            use_random = input(f"使用数据库中的随机码 (y/n) [当前: {'y' if settings.referrals_use_random_from_db else 'n'}]: ").strip().lower()
            if use_random in ["y", "n"]:
                current_settings["referrals"]["use_random_from_db"] = (use_random == "y")
            
            # 仅使用文件中的码
            use_only_file = input(f"仅使用文件中的码 (y/n) [当前: {'y' if settings.referrals_use_only_file_codes else 'n'}]: ").strip().lower()
            if use_only_file in ["y", "n"]:
                current_settings["referrals"]["use_only_file_codes"] = (use_only_file == "y")

        # 保存更新后的设置
        write_json(path=SETTINGS_FILE, obj=current_settings, indent=2)
        console.print("\n[bold green]设置已成功更新[/]")

        
    except Exception as e:
        logger.error(f"更新设置时出错: {str(e)}")
        console.print(f"\n[bold red]更新设置时出错: {str(e)}[/]")

async def option_manage_resources():
    """资源管理（代理、Twitter 令牌）"""
    try:
        
        resource_manager = ResourceManager()
        
        while True:
            # 获取不良资源统计
            bad_proxies_count, bad_twitter_count = await resource_manager.get_bad_resources_stats()
            
            # 获取可用备用资源数量
            reserve_proxies = resource_manager._load_from_file(config.RESERVE_PROXY_FILE)
            reserve_twitter = resource_manager._load_from_file(config.RESERVE_TWITTER_FILE)
            
            console.print("\n[bold cyan]资源管理[/]")
            console.print(f"发现 [red]{bad_proxies_count}[/] 个不良代理和 [red]{bad_twitter_count}[/] 个不良 Twitter 令牌")
            console.print(f"可用 [green]{len(reserve_proxies)}[/] 个备用代理和 [green]{len(reserve_twitter)}[/] 个备用 Twitter 令牌")
            
            # 菜单
            menu = Table(show_header=False, box=None)
            menu.add_column("选项", style="cyan")
            menu.add_column("描述", style="white")
            
            menu.add_row("1)", "显示不良代理")
            menu.add_row("2)", "显示不良 Twitter 令牌")
            menu.add_row("3)", "替换不良代理")
            menu.add_row("4)", "替换不良 Twitter 令牌")
            menu.add_row("5)", "替换所有不良资源")
            menu.add_row("6)", "返回")
            
            console.print(menu)
            
            choice = input("\n> ")
            
            if choice == "1":
                # 显示不良代理
                console.print("\n[bold]不良代理:[/]")
                
                bad_proxies = await resource_manager.get_bad_proxies()
                
                if bad_proxies:
                    for wallet in bad_proxies:
                        short_key = f"{wallet.public_key[:6]}...{wallet.public_key[-4:]}"
                        console.print(f" - ID: {wallet.id}, 钱包: {short_key}, 代理: {wallet.proxy}")
                else:
                    console.print("[green]没有不良代理[/]")
                
                input("\n按 Enter 继续...")
                
            elif choice == "2":
                # 显示不良 Twitter 令牌
                console.print("\n[bold]不良 Twitter 令牌:[/]")
                
                bad_twitter = await resource_manager.get_bad_twitter()
                
                if bad_twitter:
                    for wallet in bad_twitter:
                        short_key = f"{wallet.public_key[:6]}...{wallet.public_key[-4:]}"
                        console.print(f" - ID: {wallet.id}, 钱包: {short_key}")
                else:
                    console.print("[green]没有不良 Twitter 令牌[/]")
                
                input("\n按 Enter 继续...")
                
            elif choice == "3":
                # 替换不良代理
                console.print("\n[bold]替换不良代理...[/]")
                
                if len(reserve_proxies) == 0:
                    console.print("[red]错误:[/] 没有可用的备用代理文件 reserve_proxy.txt")
                    input("\n按 Enter 继续...")
                    continue
                
                if bad_proxies_count == 0:
                    console.print("[green]没有不良代理需要替换[/]")
                    input("\n按 Enter 继续...")
                    continue
                
                if len(reserve_proxies) < bad_proxies_count:
                    console.print(f"[yellow]注意:[/] 可用备用代理数量不足，可用 {len(reserve_proxies)}，需要 {bad_proxies_count}")
                
                # 请求确认
                confirm = input("继续替换吗？ (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
                
                # 执行替换
                replaced, total = await resource_manager.replace_all_bad_proxies()
                
                console.print(f"[green]替换了 {replaced} 个，共 {total} 个不良代理[/]")
                input("\n按 Enter 继续...")
                
            elif choice == "4":
                # 替换不良 Twitter 令牌
                console.print("\n[bold]替换不良 Twitter 令牌...[/]")
                
                if len(reserve_twitter) == 0:
                    console.print("[red]错误:[/] 没有可用的备用 Twitter 令牌文件 reserve_twitter.txt")
                    input("\n按 Enter 继续...")
                    continue
                
                if bad_twitter_count == 0:
                    console.print("[green]没有不良 Twitter 令牌需要替换[/]")
                    input("\n按 Enter 继续...")
                    continue
                
                if len(reserve_twitter) < bad_twitter_count:
                    console.print(f"[yellow]注意:[/] 可用备用 Twitter 令牌数量不足，可用 {len(reserve_twitter)}，需要 {bad_twitter_count}")
                
                # 请求确认
                confirm = input("继续替换吗？ (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
                
                # 执行替换
                replaced, total = await resource_manager.replace_all_bad_twitter()
                
                console.print(f"[green]替换了 {replaced} 个，共 {total} 个不良 Twitter 令牌[/]")
                input("\n按 Enter 继续...")
                
            elif choice == "5":
                # 替换所有不良资源
                console.print("\n[bold]替换所有不良资源...[/]")
                
                if len(reserve_proxies) == 0 and len(reserve_twitter) == 0:
                    console.print("[red]错误:[/] 没有可用备用资源")
                    input("\n按 Enter 继续...")
                    continue
                
                if bad_proxies_count == 0 and bad_twitter_count == 0:
                    console.print("[green]没有不良资源需要替换[/]")
                    input("\n按 Enter 继续...")
                    continue
                
                # 显示警告
                if len(reserve_proxies) < bad_proxies_count:
                    console.print(f"[yellow]注意:[/] 可用备用代理数量不足，可用 {len(reserve_proxies)}，需要 {bad_proxies_count}")
                
                if len(reserve_twitter) < bad_twitter_count:
                    console.print(f"[yellow]注意:[/] 可用备用 Twitter 令牌数量不足，可用 {len(reserve_twitter)}，需要 {bad_twitter_count}")
                
                # 请求确认
                confirm = input("继续替换吗？ (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
                
                # 执行替换所有资源
                proxies_replaced, proxies_total = await resource_manager.replace_all_bad_proxies()
                twitter_replaced, twitter_total = await resource_manager.replace_all_bad_twitter()
                
                console.print(f"[green]替换了 {proxies_replaced} 个，共 {proxies_total} 个不良代理[/]")
                console.print(f"[green]替换了 {twitter_replaced} 个，共 {twitter_total} 个不良 Twitter 令牌[/]")
                input("\n按 Enter 继续...")
                
            elif choice == "6":
                # 返回
                return
                
            else:
                console.print("\n[bold yellow]无效选择。请选择 1-6 之间的操作。[/]")
                input("按 Enter 继续...")
                
    except Exception as e:
        logger.error(f"资源管理时出错: {str(e)}")
        console.print(f"\n[bold red]资源管理时出错: {str(e)}[/]")
        input("按 Enter 继续...")

async def option_manage_refcodes():
    """管理推荐码"""
    try:
        while True:
            # 从文件加载代码
            file_codes = load_ref_codes()
            
            # 从数据库获取代码
            async with Session() as session:
                db = DB(session=session)
                db_codes = await db.get_available_ref_codes()
            
            console.print("\n[bold cyan]管理推荐码[/]")
            console.print(f"发现 [green]{len(file_codes)}[/] 个代码在文件中，[green]{len(db_codes)}[/] 个代码在数据库中")
            
            # 菜单
            menu = Table(show_header=False, box=None)
            menu.add_column("选项", style="cyan")
            menu.add_column("描述", style="white")
            
            menu.add_row("1)", "显示文件中的代码")
            menu.add_row("2)", "显示数据库中的代码")
            menu.add_row("3)", "将代码添加到文件中")
            menu.add_row("4)", "从数据库更新文件中的代码")
            menu.add_row("5)", "返回")
            
            console.print(menu)
            
            choice = input("\n> ")
            
            if choice == "1":
                # 显示文件中的代码
                console.print("\n[bold]推荐码从文件中:[/]")
                
                if file_codes:
                    for i, code in enumerate(file_codes, 1):
                        console.print(f" {i}. {code}")
                else:
                    console.print("[yellow]推荐码文件为空[/]")
                
                input("\n按 Enter 继续...")
                
            elif choice == "2":
                # 显示数据库中的代码
                console.print("\n[bold]推荐码从数据库中:[/]")
                
                if db_codes:
                    for i, code in enumerate(db_codes, 1):
                        console.print(f" {i}. {code}")
                else:
                    console.print("[yellow]数据库中没有推荐码[/]")
                
                input("\n按 Enter 继续...")
                
            elif choice == "3":
                # 将代码添加到文件中
                console.print("\n[bold]将代码添加到文件中:[/]")
                
                new_code = input("输入推荐码: ").strip()
                
                if new_code:
                    success = await add_ref_code_to_file(new_code)
                    if success:
                        console.print(f"[green]代码 {new_code} 已成功添加到文件中[/]")
                    else:
                        console.print(f"[red]添加代码 {new_code} 到文件时出错[/]")
                else:
                    console.print("[yellow]代码不能为空[/]")
                
                input("\n按 Enter 继续...")
                
            elif choice == "4":
                # 从数据库更新文件中的代码
                console.print("\n[bold]从数据库更新文件中的代码:[/]")
                
                if not db_codes:
                    console.print("[yellow]数据库中没有推荐码[/]")
                    input("\n按 Enter 继续...")
                    continue
                
                confirm = input("此操作将覆盖文件中的所有代码。继续吗？ (y/n): ").strip().lower()
                
                if confirm == 'y':
                    success = await update_ref_codes_file_from_db()
                    if success:
                        console.print(f"[green]文件已更新，添加了 {len(db_codes)} 个代码[/]")
                    else:
                        console.print("[red]更新文件中的代码时出错[/]")
                
                input("\n按 Enter 继续...")
                
            elif choice == "5":
                # 返回
                return
                
            else:
                console.print("\n[bold yellow]无效选择。请选择 1-5 之间的操作。[/]")
                input("按 Enter 继续...")
                
    except Exception as e:
        logger.error(f"管理推荐码时出错: {str(e)}")
        console.print(f"\n[bold red]管理推荐码时出错: {str(e)}[/]")
        input("按 Enter 继续...")

def print_menu():
    """显示程序菜单"""
    menu = Table(show_header=False, box=None)
    menu.add_column("选项", style="cyan")
    menu.add_column("描述", style="white")
    
    menu.add_row("1)", "将钱包导入数据库")
    menu.add_row("2)", "完成所有钱包任务")
    menu.add_row("3)", "完成选定任务")
    menu.add_row("4)", "显示统计")
    menu.add_row("5)", "资源管理")  # 新菜单项
    menu.add_row("6)", "管理推荐码")  # 新菜单项
    menu.add_row("7)", "设置")
    menu.add_row("8)", "退出")
    
    console.print(menu)

async def main():
    """主程序函数"""
    # 初始化文件和数据库
    create_files()
    from utils.db_api_async.db_init import init_db
    # await init_db()
    migration_dir = Path('./migrations')
    has_migrations = migration_dir.exists()
    
    await init_db()
    
    # 如果存在迁移目录，检查所有更新是否成功
    if has_migrations:
        from utils.db_api_async.db_migrator import check_and_migrate_db
        migration_success = await check_and_migrate_db()
        
        # if not migration_success:
        #     console.print("\n[bold yellow]警告: 数据库结构更新可能不完整。[/]")
        #     console.print("[bold yellow]如果程序运行不稳定，请尝试创建新的数据库。[/]")
        #     input("按 Enter 继续...")
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')  # 清除控制台
        print_logo()
        print_menu()
        
        try:
            action = input("\n> ")
            
            if action == "1":
                # 将钱包导入数据库
                console.print("\n[bold cyan]将钱包导入数据库...[/]")
                await add_wallets_db()
                console.print("[bold green]导入完成。按 Enter 继续...[/]")
                input()
                
            elif action == "2":
                # 完成所有任务
                console.print("\n[bold cyan]完成所有任务...[/]")
                await complete_all_wallets_quests()
                console.print("[bold green]完成任务完成。按 Enter 继续...[/]")
                input()
                
            elif action == "3":
                # 完成选定任务
                console.print("\n[bold cyan]完成选定任务...[/]")
                await complete_specific_quests()
                console.print("[bold green]完成任务完成。按 Enter 继续...[/]")
                input()
                
            elif action == "4":
                # 显示统计
                console.print("\n[bold cyan]获取统计...[/]")
                await get_wallets_stats()
                console.print("[bold green]按 Enter 继续...[/]")
                input()
                
            elif action == "5":
                # 资源管理（新选项）
                await option_manage_resources()

            elif action == "6":
                # 管理推荐码（新选项）
                await option_manage_refcodes()
                
            elif action == "7":
                # 设置
                await option_update_settings()
                sys.exit(0)
                
            elif action == "8":
                # 退出
                console.print("\n[bold cyan]退出程序[/]")
                sys.exit(0)
            else:
                console.print("\n[bold yellow]无效选择。请选择 1-8 之间的操作。[/]")
                input("按 Enter 继续...")
                
        except KeyboardInterrupt:
            console.print("\n[bold cyan]退出程序。[/]")
            sys.exit(0)
        except ValueError as err:
            logger.error(f'输入数据错误: {err}')
            console.print(f"\n[bold red]输入数据错误: {err}[/]")
            input("按 Enter 继续...")
        except Exception as e:
            logger.error(f'意外错误: {e}')
            console.print(f"\n[bold red]意外错误: {e}[/]")
            input("按 Enter 继续...")

if __name__ == "__main__":
    try:
        # # 设置日志
        # logger.remove()  # 删除默认处理程序
        # # 仅添加必要的日志级别
        # logger.add(
        #     "files/errors.log", 
        #     level="ERROR", 
        #     format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
        # )
        # logger.add(
        #     "files/log.log", 
        #     level="INFO",
        #     format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        #     filter=lambda record: record["level"].name == "INFO" or record["level"].name == "SUCCESS"
        # )
        
        # 运行程序
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold cyan]程序完成![/]")
        sys.exit(0)
