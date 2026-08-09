from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, select
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import get_settings


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=False,
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    first_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


async def init_db() -> None:
    """Crea le tabelle mancanti."""

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def register_user(
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    is_admin: bool,
) -> User:
    """Registra l'utente oppure aggiorna i suoi dati."""

    async with SessionLocal() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_user_id == telegram_user_id
            )
        )

        user = result.scalar_one_or_none()

        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
                is_admin=is_admin,
            )

            session.add(user)

        else:
            user.username = username
            user.first_name = first_name
            user.is_admin = is_admin
            user.updated_at = datetime.now(timezone.utc)

        await session.commit()

        return user
