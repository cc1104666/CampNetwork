import os
import sys
import asyncio
import subprocess
from pathlib import Path
from loguru import logger

async def check_and_migrate_db():
    """
    检查数据库结构并执行必要的迁移
    """
    try:
        logger.info("检查数据库结构...")
        
        # 确定数据库路径
        db_path = Path('./files/wallets.db')
        
        # 检查数据库是否存在
        if not db_path.exists():
            logger.info("数据库不存在，创建新数据库")
            # 新数据库将使用最新架构创建
            return True
        
        # 检查 migrations 目录是否存在
        migration_dir = Path('./migrations')
        if not migration_dir.exists():
            logger.warning("未找到迁移目录，跳过迁移检查")
            return True
        
        # 执行 Alembic 命令检查迁移状态
        logger.info("运行 Alembic 迁移...")
        try:
            # 为了在 venv 或冻结应用程序中正常工作
            python_exe = sys.executable
            
            # 通过 subprocess 执行迁移
            process = subprocess.Popen(
                [python_exe, "-m", "alembic", "upgrade", "head"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                logger.success("数据库迁移成功完成")
                if stdout:
                    logger.info(f"迁移结果: {stdout}")
                return True
            else:
                # logger.error(f"执行迁移时出错: {stderr}")
                
                # 如果错误与 alembic_version 表不存在有关，
                # 说明这是从旧数据库的第一次更新
                if "alembic_version" in stderr:
                    logger.warning("检测到旧数据库结构，尝试更新...")
                    
                    # 执行第一次迁移命令，标记为"数据已创建"
                    process = subprocess.Popen(
                        [python_exe, "-m", "alembic", "stamp", "head"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    stdout, stderr = process.communicate()
                    
                    if process.returncode == 0:
                        logger.success("数据库已标记为最新")
                        
                        # 现在手动添加缺失的 ref_code 字段
                        from sqlite3 import connect
                        conn = connect(str(db_path))
                        cursor = conn.cursor()
                        
                        # 检查是否已有 ref_code 字段
                        cursor.execute("PRAGMA table_info(campnetwork)")
                        columns = [col[1] for col in cursor.fetchall()]
                        
                        if "ref_code" not in columns:
                            logger.info("向 campnetwork 表添加 ref_code 字段")
                            cursor.execute("ALTER TABLE campnetwork ADD COLUMN ref_code TEXT")
                            conn.commit()
                            logger.success("ref_code 字段添加成功")
                        
                        conn.close()
                        return True
                    else:
                        # logger.error(f"更新数据库结构时出错: {stderr}")
                        return False
                
                return False
                
        except Exception as e:
            # logger.error(f"执行迁移时出错: {str(e)}")
            
            # 如果无法通过 Alembic 执行迁移，
            # 尝试手动添加字段
            return True
        
    except Exception as e:
        return True
