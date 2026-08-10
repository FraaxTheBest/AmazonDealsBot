from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from decimal import Decimal
from typing import Iterable

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    delete,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.amazon.models import (
    ProductSnapshot,
)
from app.autopost_store import (
    ChannelAutopostConfig,
    get_or_create_autopost_config,
)
from app.database import (
    Base,
    Channel,
    SessionLocal,
    User,
)


# =========================================================
# MODELLO DATABASE
# =========================================================


class PublicationEvent(Base):
    """
    Storico delle pubblicazioni.

    Ogni riga rappresenta
    una pubblicazione di un ASIN
    in uno specifico canale.
    """

    __tablename__ = (
        "publication_events"
    )

    __table_args__ = (
        Index(
            "ix_publication_events_"
            "channel_asin_date",
            "channel_id",
            "asin",
            "published_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    channel_id: Mapped[int] = (
        mapped_column(
            ForeignKey("channels.id"),
            nullable=False,
            index=True,
        )
    )

    asin: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = (
        mapped_column(
            String(500),
            nullable=True,
        )
    )

    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="autopost",
    )

    current_price: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    discount_percentage: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(5, 2),
        nullable=True,
    )

    telegram_message_id: Mapped[
        int | None
    ] = mapped_column(
        BigInteger,
        nullable=True,
    )

    published_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(
            timezone.utc
        ),
        nullable=False,
        index=True,
    )


# =========================================================
# RISULTATO ANTI-DUP
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class DuplicateProduct:
    product: ProductSnapshot

    last_published_at: datetime


@dataclass(
    frozen=True,
    slots=True,
)
class DedupeResult:
    total_count: int

    passed_products: tuple[
        ProductSnapshot,
        ...
    ]

    duplicate_products: tuple[
        DuplicateProduct,
        ...
    ]

    @property
    def passed_count(
        self,
    ) -> int:
        return len(
            self.passed_products
        )

    @property
    def duplicate_count(
        self,
    ) -> int:
        return len(
            self.duplicate_products
        )


# =========================================================
# HELPERS
# =========================================================


def normalize_utc(
    value: datetime,
) -> datetime:
    """
    SQLite può restituire datetime
    senza timezone.
    """

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


async def get_owned_channel(
    owner_telegram_user_id: int,
    channel_id: int,
) -> Channel | None:
    async with SessionLocal() as session:
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


# =========================================================
# CONFIGURAZIONE FINESTRA
# =========================================================


async def set_dedupe_window_hours(
    owner_telegram_user_id: int,
    channel_id: int,
    hours: int,
) -> ChannelAutopostConfig:
    """
    0 = anti-duplicati disattivato.

    Massimo:
    8760 ore = circa 1 anno.
    """

    if (
        hours < 0
        or hours > 8760
    ):
        raise ValueError(
            "La finestra anti-duplicati "
            "deve essere tra 0 "
            "e 8760 ore."
        )

    await get_or_create_autopost_config(
        owner_telegram_user_id,
        channel_id,
    )

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                ChannelAutopostConfig
            )
            .join(
                Channel,
                ChannelAutopostConfig
                .channel_id
                == Channel.id,
            )
            .join(
                User,
                Channel.owner_id
                == User.id,
            )
            .where(
                Channel.id
                == channel_id,
                User.telegram_user_id
                == (
                    owner_telegram_user_id
                ),
            )
        )

        config = (
            result.scalar_one_or_none()
        )

        if config is None:
            raise ValueError(
                "Configurazione "
                "non trovata."
            )

        config.dedupe_window_hours = (
            hours
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


# =========================================================
# REGISTRA PUBBLICAZIONE
# =========================================================


async def record_publication(
    owner_telegram_user_id: int,
    channel_id: int,
    product: ProductSnapshot,
    source: str,
    telegram_message_id: (
        int | None
    ) = None,
) -> PublicationEvent:
    """
    Registra un prodotto come
    pubblicato nel canale.

    source potrà essere:
    - manual
    - scheduled
    - autopost
    - test
    """

    channel = await get_owned_channel(
        owner_telegram_user_id,
        channel_id,
    )

    if channel is None:
        raise ValueError(
            "Canale non disponibile."
        )

    normalized_asin = (
        product.asin
        .strip()
        .upper()
    )

    async with SessionLocal() as session:
        event = PublicationEvent(
            channel_id=channel.id,
            asin=normalized_asin,
            title=product.title,
            source=source,
            current_price=(
                product.current_price
            ),
            discount_percentage=(
                product
                .discount_percentage
            ),
            telegram_message_id=(
                telegram_message_id
            ),
            published_at=(
                datetime.now(
                    timezone.utc
                )
            ),
        )

        session.add(
            event
        )

        await session.commit()

        await session.refresh(
            event
        )

        return event


# =========================================================
# FILTRO ANTI-DUPLICATI
# =========================================================


async def filter_recent_duplicates(
    owner_telegram_user_id: int,
    channel_id: int,
    products: Iterable[
        ProductSnapshot
    ],
    window_hours: int,
) -> DedupeResult:
    product_list = tuple(
        products
    )

    if not product_list:
        return DedupeResult(
            total_count=0,
            passed_products=(),
            duplicate_products=(),
        )

    channel = await get_owned_channel(
        owner_telegram_user_id,
        channel_id,
    )

    if channel is None:
        raise ValueError(
            "Canale non disponibile."
        )

    #
    # 0 = anti-duplicati OFF.
    #
    if window_hours <= 0:
        return DedupeResult(
            total_count=len(
                product_list
            ),
            passed_products=(
                product_list
            ),
            duplicate_products=(),
        )

    asin_values = {
        product.asin
        .strip()
        .upper()
        for product in product_list
    }

    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            hours=window_hours
        )
    )

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                PublicationEvent
            )
            .where(
                PublicationEvent
                .channel_id
                == channel.id,
                PublicationEvent
                .asin
                .in_(asin_values),
                PublicationEvent
                .published_at
                >= cutoff,
            )
            .order_by(
                PublicationEvent
                .published_at
                .desc()
            )
        )

        events = list(
            result.scalars().all()
        )

    #
    # Teniamo solo l'ultima
    # pubblicazione per ASIN.
    #
    latest_by_asin: dict[
        str,
        datetime,
    ] = {}

    for event in events:
        asin = (
            event.asin
            .strip()
            .upper()
        )

        if asin not in latest_by_asin:
            latest_by_asin[asin] = (
                normalize_utc(
                    event.published_at
                )
            )

    passed: list[
        ProductSnapshot
    ] = []

    duplicates: list[
        DuplicateProduct
    ] = []

    for product in product_list:
        asin = (
            product.asin
            .strip()
            .upper()
        )

        last_published = (
            latest_by_asin.get(
                asin
            )
        )

        if last_published is None:
            passed.append(
                product
            )

        else:
            duplicates.append(
                DuplicateProduct(
                    product=product,
                    last_published_at=(
                        last_published
                    ),
                )
            )

    return DedupeResult(
        total_count=len(
            product_list
        ),
        passed_products=tuple(
            passed
        ),
        duplicate_products=tuple(
            duplicates
        ),
    )


# =========================================================
# STORICO
# =========================================================


async def list_recent_publications(
    owner_telegram_user_id: int,
    channel_id: int,
    limit: int = 20,
) -> list[
    PublicationEvent
]:
    channel = await get_owned_channel(
        owner_telegram_user_id,
        channel_id,
    )

    if channel is None:
        raise ValueError(
            "Canale non disponibile."
        )

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                PublicationEvent
            )
            .where(
                PublicationEvent
                .channel_id
                == channel.id
            )
            .order_by(
                PublicationEvent
                .published_at
                .desc()
            )
            .limit(
                max(
                    1,
                    min(limit, 100),
                )
            )
        )

        return list(
            result.scalars().all()
        )


async def clear_test_publications(
    owner_telegram_user_id: int,
    channel_id: int,
) -> int:
    """
    Cancella esclusivamente
    record source=test.

    Non tocca pubblicazioni reali.
    """

    channel = await get_owned_channel(
        owner_telegram_user_id,
        channel_id,
    )

    if channel is None:
        raise ValueError(
            "Canale non disponibile."
        )

    async with SessionLocal() as session:
        result = await session.execute(
            delete(
                PublicationEvent
            ).where(
                PublicationEvent
                .channel_id
                == channel.id,
                PublicationEvent
                .source
                == "test",
            )
        )

        await session.commit()

        return int(
            result.rowcount or 0
        )
