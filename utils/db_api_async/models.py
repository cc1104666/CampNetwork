from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Text


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'soneium'

    id: Mapped[int] = mapped_column(primary_key=True)
    private_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    public_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    proxy: Mapped[str] = mapped_column(Text, nullable=True, unique=False)
    user_agent: Mapped[str] = mapped_column(Text, nullable=False, unique=False)

    def __str__(self):
        return f'{self.public_key}'

    def __repr__(self):
        return f'{self.public_key}'
