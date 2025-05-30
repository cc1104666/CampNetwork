from .db_api import async_engine
from .models import Base
from .db_migrator import check_and_migrate_db
from loguru import logger

# 异步初始化数据库
async def init_db():
    migration_success = await check_and_migrate_db()
    
    async with async_engine.begin() as conn:
        # 创建表
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

