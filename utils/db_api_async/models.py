from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text, ARRAY, String

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'campnetwork'

    id: Mapped[int] = mapped_column(primary_key=True)
    private_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    proxy: Mapped[str] = mapped_column(Text, nullable=True, unique=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False, unique=False)
    completed_quests: Mapped[str] = mapped_column(Text, nullable=True, default="")  # 使用分隔符的字符串
    twitter_token: Mapped[str] = mapped_column(Text, nullable=True, default=None)  # 添加 Twitter 令牌字段
    proxy_status: Mapped[str] = mapped_column(Text, nullable=True, default="OK")  # 代理状态 (OK/BAD)
    twitter_status: Mapped[str] = mapped_column(Text, nullable=True, default="OK")  # Twitter 令牌状态 (OK/BAD)
    ref_code: Mapped[str] = mapped_column(Text, nullable=True, default=None)

    def __str__(self):
        return f'{self.public_key}'

    def __repr__(self):
        return f'{self.public_key}'
