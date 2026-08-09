from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.database import (
    Base,
    SessionLocal,
    User,
)


class PostTemplate(Base):
    __tablename__ = "post_templates"

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

    # Per ora usiamo il template globale.
    # Questo campo ci permetterà in futuro
    # di avere template diversi per canale.
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(100),
        default="Default",
        nullable=False,
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        onupdate=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )


async def get_owner(
    session: AsyncSession,
    telegram_user_id: int,
) -> User:
    result = await session.execute(
        select(User).where(
            User.telegram_user_id
            == telegram_user_id
        )
    )

    owner = result.scalar_one_or_none()

    if owner is None:
        raise ValueError(
            "Utente amministratore "
            "non registrato."
        )

    return owner


async def get_default_template(
    owner_telegram_user_id: int,
    default_content: str,
) -> PostTemplate:
    """
    Recupera il template globale.

    Se non esiste ancora lo crea
    automaticamente con il contenuto default.
    """

    async with SessionLocal() as session:
        owner = await get_owner(
            session,
            owner_telegram_user_id,
        )

        result = await session.execute(
            select(PostTemplate)
            .where(
                PostTemplate.owner_id
                == owner.id,
                PostTemplate.channel_id
                .is_(None),
                PostTemplate.is_active
                .is_(True),
            )
            .order_by(PostTemplate.id)
        )

        template = (
            result.scalars().first()
        )

        if template is None:
            template = PostTemplate(
                owner_id=owner.id,
                channel_id=None,
                name="Default",
                content=default_content,
                is_active=True,
            )

            session.add(template)

            await session.commit()
            await session.refresh(template)

        return template


async def get_default_template_content(
    owner_telegram_user_id: int,
    default_content: str,
) -> str:
    template = await get_default_template(
        owner_telegram_user_id,
        default_content,
    )

    return template.content


async def save_default_template(
    owner_telegram_user_id: int,
    content: str,
    default_content: str,
) -> PostTemplate:
    """
    Salva il template globale.
    """

    async with SessionLocal() as session:
        owner = await get_owner(
            session,
            owner_telegram_user_id,
        )

        result = await session.execute(
            select(PostTemplate)
            .where(
                PostTemplate.owner_id
                == owner.id,
                PostTemplate.channel_id
                .is_(None),
                PostTemplate.is_active
                .is_(True),
            )
            .order_by(PostTemplate.id)
        )

        template = (
            result.scalars().first()
        )

        if template is None:
            template = PostTemplate(
                owner_id=owner.id,
                channel_id=None,
                name="Default",
                content=content
                or default_content,
                is_active=True,
            )

            session.add(template)

        else:
            template.content = (
                content or default_content
            )

            template.updated_at = (
                datetime.now(
                    timezone.utc
                )
            )

        await session.commit()
        await session.refresh(template)

        return template


async def reset_default_template(
    owner_telegram_user_id: int,
    default_content: str,
) -> PostTemplate:
    return await save_default_template(
        owner_telegram_user_id=(
            owner_telegram_user_id
        ),
        content=default_content,
        default_content=default_content,
    )
