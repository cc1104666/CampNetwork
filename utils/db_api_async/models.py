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
    completed_quests: Mapped[str] = mapped_column(Text, nullable=True, default="")  # Просто строка с разделителями
    twitter_token: Mapped[str] = mapped_column(Text, nullable=True, default=None)  # Добавляем поле для Twitter токена
    proxy_status: Mapped[str] = mapped_column(Text, nullable=True, default="OK")  # Статус прокси (OK/BAD)
    twitter_status: Mapped[str] = mapped_column(Text, nullable=True, default="OK")  # Статус токена Twitter (OK/BAD)

    def __str__(self):
        return f'{self.public_key}'

    def __repr__(self):
        return f'{self.public_key}'
