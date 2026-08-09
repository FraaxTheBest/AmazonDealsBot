from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    select,
)
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


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    telegram_chat_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    can_post_messages: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
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
    """Registra o aggiorna un utente."""

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


async def save_channel(
    owner_telegram_user_id: int,
    telegram_chat_id: int,
    title: str,
    username: str | None,
    can_post_messages: bool,
) -> Channel:
    """Salva oppure aggiorna un canale."""

    async with SessionLocal() as session:
        owner_result = await session.execute(
            select(User).where(
                User.telegram_user_id == owner_telegram_user_id
            )
        )

        owner = owner_result.scalar_one_or_none()

        if owner is None:
            raise ValueError("Utente proprietario non registrato.")

        result = await session.execute(
            select(Channel).where(
                Channel.telegram_chat_id == telegram_chat_id
            )
        )

        channel = result.scalar_one_or_none()

        if channel is None:
            channel = Channel(
                owner_id=owner.id,
                telegram_chat_id=telegram_chat_id,
                title=title,
                username=username,
                can_post_messages=can_post_messages,
                is_active=True,
            )

            session.add(channel)

        else:
            channel.owner_id = owner.id
            channel.title = title
            channel.username = username
            channel.can_post_messages = can_post_messages
            channel.is_active = True
            channel.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(channel)

        return channel


async def list_channels(
    owner_telegram_user_id: int,
) -> list[Channel]:
    """Restituisce i canali attivi dell'utente."""

    async with SessionLocal() as session:
        result = await session.execute(
            select(Channel)
            .join(
                User,
                Channel.owner_id == User.id,
            )
            .where(
                User.telegram_user_id
                == owner_telegram_user_id,
                Channel.is_active.is_(True),
            )
            .order_by(Channel.title)
        )

        return list(result.scalars().all())


async def get_channel(
    channel_id: int,
    owner_telegram_user_id: int,
) -> Channel | None:
    """Restituisce un canale appartenente all'utente."""

    async with SessionLocal() as session:
        result = await session.execute(
            select(Channel)
            .join(
                User,
                Channel.owner_id == User.id,
            )
            .where(
                Channel.id == channel_id,
                User.telegram_user_id
                == owner_telegram_user_id,
                Channel.is_active.is_(True),
            )
        )

        return result.scalar_one_or_none()


async def disable_channel(
    channel_id: int,
    owner_telegram_user_id: int,
) -> bool:
    """Disattiva un canale senza cancellarne i dati."""

    async with SessionLocal() as session:
        result = await session.execute(
            select(Channel)
            .join(
                User,
                Channel.owner_id == User.id,
            )
            .where(
                Channel.id == channel_id,
                User.telegram_user_id
                == owner_telegram_user_id,
            )
        )

        channel = result.scalar_one_or_none()

        if channel is None:
            return False

        channel.is_active = False
        channel.updated_at = datetime.now(timezone.utc)

        await session.commit()

        return True
