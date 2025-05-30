from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

# 修复 MySQL 连接字符串


# 创建异步引擎
async_engine = create_async_engine(
    'sqlite+aiosqlite:///./files/wallets.db',
    echo=False,  # 可以开启用于调试
)

# 创建异步会话工厂
async_session = async_sessionmaker(
    bind=async_engine, expire_on_commit=False, class_=AsyncSession
)


class Session:
    def __init__(self):
        self.session = async_session()

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            await self.session.commit()
        except Exception as e:
            await self.session.rollback()
            return e
        finally:
            await self.session.close()
