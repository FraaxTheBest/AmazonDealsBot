import json
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.categories import (
    normalize_categories,
)
from app.database import (
    Base,
    Channel,
    SessionLocal,
    User,
)


class ChannelAutopostConfig(Base):
    __tablename__ = (
        "channel_autopost_configs"
    )

    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            name=(
                "uq_channel_autopost_"
                "config_channel"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"),
        nullable=False,
        unique=True,
        index=True,
    )

    # -----------------------------------------------------
    # AUTOPOST
    # -----------------------------------------------------

    is_enabled: Mapped[bool] = (
        mapped_column(
            Boolean,
            default=False,
            nullable=False,
        )
    )

    # -----------------------------------------------------
    # CATEGORIE - FASE 9A
    #
    # [] = tutte le categorie
    # -----------------------------------------------------

    categories_json: Mapped[str] = (
        mapped_column(
            Text,
            default="[]",
            nullable=False,
        )
    )

    # -----------------------------------------------------
    # FILTRI - FASE 9B
    # -----------------------------------------------------

    min_discount_percentage: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(5, 2),
        default=Decimal("10"),
        nullable=False,
    )

    min_score: Mapped[int] = (
        mapped_column(
            Integer,
            default=60,
            nullable=False,
        )
    )

    min_rating: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(3, 2),
        nullable=True,
    )

    min_reviews: Mapped[
        int | None
    ] = mapped_column(
        Integer,
        nullable=True,
    )

    min_price: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    max_price: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    require_amazon_shipping: Mapped[
        bool
    ] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # -----------------------------------------------------
    # ANTI DUPLICATI - FASE 9C
    # -----------------------------------------------------

    dedupe_window_hours: Mapped[int] = (
        mapped_column(
            Integer,
            default=168,
            nullable=False,
        )
    )

    created_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )

    updated_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        onupdate=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
    )


async def _get_owned_channel(
    session,
    owner_telegram_user_id: int,
    channel_id: int,
) -> Channel | None:
    result = await session.execute(
        select(Channel)
        .join(
            User,
            Channel.owner_id
            == User.id,
        )
        .where(
            Channel.id
            == channel_id,
            User.telegram_user_id
            == owner_telegram_user_id,
            Channel.is_active
            .is_(True),
        )
    )

    return (
        result.scalar_one_or_none()
    )


async def get_or_create_autopost_config(
    owner_telegram_user_id: int,
    channel_id: int,
) -> ChannelAutopostConfig:
    async with SessionLocal() as session:
        channel = await _get_owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )

        if channel is None:
            raise ValueError(
                "Canale non disponibile."
            )

        result = await session.execute(
            select(
                ChannelAutopostConfig
            ).where(
                ChannelAutopostConfig
                .channel_id
                == channel.id
            )
        )

        config = (
            result.scalar_one_or_none()
        )

        if config is None:
            config = (
                ChannelAutopostConfig(
                    channel_id=channel.id
                )
            )

            session.add(
                config
            )

            await session.commit()

            await session.refresh(
                config
            )

        return config


def get_selected_categories(
    config: ChannelAutopostConfig,
) -> tuple[str, ...]:
    try:
        values = json.loads(
            config.categories_json
        )

    except (
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ):
        return ()

    if not isinstance(
        values,
        list,
    ):
        return ()

    return normalize_categories(
        str(value)
        for value in values
    )


async def set_selected_categories(
    owner_telegram_user_id: int,
    channel_id: int,
    categories: list[str]
    | tuple[str, ...],
) -> ChannelAutopostConfig:
    normalized = (
        normalize_categories(
            categories
        )
    )

    async with SessionLocal() as session:
        channel = await _get_owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )

        if channel is None:
            raise ValueError(
                "Canale non disponibile."
            )

        result = await session.execute(
            select(
                ChannelAutopostConfig
            ).where(
                ChannelAutopostConfig
                .channel_id
                == channel.id
            )
        )

        config = (
            result.scalar_one_or_none()
        )

        if config is None:
            config = (
                ChannelAutopostConfig(
                    channel_id=channel.id
                )
            )

            session.add(
                config
            )

        config.categories_json = (
            json.dumps(
                list(normalized),
                ensure_ascii=False,
            )
        )

        config.updated_at = (
            datetime.now(
                timezone.utc
            )
        )

        await session.commit()

        await session.refresh(
            config
        )

        return config
