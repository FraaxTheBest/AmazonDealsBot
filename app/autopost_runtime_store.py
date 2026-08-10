from dataclasses import dataclass
from datetime import (
    datetime,
    timezone,
)

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
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
# DEFAULT
# =========================================================


DEFAULT_SCAN_INTERVAL_MINUTES = 30

DEFAULT_PUBLISH_INTERVAL_MINUTES = 60

DEFAULT_MAX_CANDIDATES_PER_SCAN = 5


# =========================================================
# MODELLO DATABASE
# =========================================================


class ChannelAutopostRuntimeConfig(
    Base
):
    """
    Configurazione operativa
    dell'Autoposting.

    Separata da ChannelAutopostConfig
    per non modificare la tabella
    SQLite già esistente.
    """

    __tablename__ = (
        "channel_autopost_runtime_configs"
    )

    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            name=(
                "uq_channel_autopost_"
                "runtime_channel"
            ),
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
            unique=True,
            index=True,
        )
    )

    # =====================================================
    # INTERVALLO SCANSIONE
    # =====================================================

    scan_interval_minutes: Mapped[
        int
    ] = mapped_column(
        Integer,
        default=(
            DEFAULT_SCAN_INTERVAL_MINUTES
        ),
        nullable=False,
    )

    # =====================================================
    # INTERVALLO PUBBLICAZIONE
    # =====================================================

    publish_interval_minutes: Mapped[
        int
    ] = mapped_column(
        Integer,
        default=(
            DEFAULT_PUBLISH_INTERVAL_MINUTES
        ),
        nullable=False,
    )

    # =====================================================
    # LIMITE CANDIDATI
    # =====================================================

    max_candidates_per_scan: Mapped[
        int
    ] = mapped_column(
        Integer,
        default=(
            DEFAULT_MAX_CANDIDATES_PER_SCAN
        ),
        nullable=False,
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


# =========================================================
# HELPERS DATABASE
# =========================================================


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


async def _get_runtime_config(
    session,
    channel_id: int,
) -> (
    ChannelAutopostRuntimeConfig
    | None
):
    result = await session.execute(
        select(
            ChannelAutopostRuntimeConfig
        )
        .where(
            ChannelAutopostRuntimeConfig
            .channel_id
            == channel_id
        )
    )

    return (
        result.scalar_one_or_none()
    )


# =========================================================
# GET / CREATE CONFIG
# =========================================================


async def get_or_create_runtime_config(
    owner_telegram_user_id: int,
    channel_id: int,
) -> ChannelAutopostRuntimeConfig:
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

        config = (
            await _get_runtime_config(
                session,
                channel.id,
            )
        )

        if config is None:
            config = (
                ChannelAutopostRuntimeConfig(
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


# =========================================================
# ON / OFF
# =========================================================


async def set_autopost_enabled(
    owner_telegram_user_id: int,
    channel_id: int,
    enabled: bool,
) -> ChannelAutopostConfig:
    """
    Utilizza il campo is_enabled
    già presente nella configurazione
    Autopost della Fase 9.
    """

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
                == owner_telegram_user_id,
                Channel.is_active
                .is_(True),
            )
        )

        config = (
            result.scalar_one_or_none()
        )

        if config is None:
            raise ValueError(
                "Configurazione "
                "Autoposting non trovata."
            )

        config.is_enabled = bool(
            enabled
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
# VALIDAZIONE
# =========================================================


RUNTIME_FIELDS = {
    "scan_interval_minutes",
    "publish_interval_minutes",
    "max_candidates_per_scan",
}


def validate_runtime_value(
    field: str,
    value: int,
) -> None:
    if field not in RUNTIME_FIELDS:
        raise ValueError(
            "Impostazione non valida."
        )

    if (
        field
        == "scan_interval_minutes"
    ):
        if (
            value < 1
            or value > 1440
        ):
            raise ValueError(
                "La scansione deve essere "
                "tra 1 e 1440 minuti."
            )

    elif (
        field
        == "publish_interval_minutes"
    ):
        if (
            value < 1
            or value > 1440
        ):
            raise ValueError(
                "L'intervallo di "
                "pubblicazione deve essere "
                "tra 1 e 1440 minuti."
            )

    elif (
        field
        == "max_candidates_per_scan"
    ):
        if (
            value < 1
            or value > 50
        ):
            raise ValueError(
                "I candidati per scansione "
                "devono essere tra 1 e 50."
            )


# =========================================================
# MODIFICA CONFIG
# =========================================================


async def set_runtime_value(
    owner_telegram_user_id: int,
    channel_id: int,
    field: str,
    value: int,
) -> ChannelAutopostRuntimeConfig:
    validate_runtime_value(
        field,
        value,
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

        config = (
            await _get_runtime_config(
                session,
                channel.id,
            )
        )

        if config is None:
            config = (
                ChannelAutopostRuntimeConfig(
                    channel_id=channel.id
                )
            )

            session.add(
                config
            )

        setattr(
            config,
            field,
            int(value),
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
# RESET
# =========================================================


async def reset_runtime_config(
    owner_telegram_user_id: int,
    channel_id: int,
) -> ChannelAutopostRuntimeConfig:
    """
    Ripristina:

    - Autopost OFF
    - scansione 30 minuti
    - pubblicazione 60 minuti
    - massimo 5 candidati
    """

    await set_autopost_enabled(
        owner_telegram_user_id,
        channel_id,
        False,
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

        config = (
            await _get_runtime_config(
                session,
                channel.id,
            )
        )

        if config is None:
            config = (
                ChannelAutopostRuntimeConfig(
                    channel_id=channel.id
                )
            )

            session.add(
                config
            )

        config.scan_interval_minutes = (
            DEFAULT_SCAN_INTERVAL_MINUTES
        )

        config.publish_interval_minutes = (
            DEFAULT_PUBLISH_INTERVAL_MINUTES
        )

        config.max_candidates_per_scan = (
            DEFAULT_MAX_CANDIDATES_PER_SCAN
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
# FASE 10B
# CANALI AUTOPOST ATTIVI
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class EnabledAutopostChannel:
    owner_telegram_user_id: int

    channel_id: int

    channel_title: str

    scan_interval_minutes: int

    publish_interval_minutes: int

    max_candidates_per_scan: int


async def list_enabled_autopost_channels(
) -> list[
    EnabledAutopostChannel
]:
    """
    Restituisce tutti i canali
    attivi con Autoposting ON.

    Serve allo scheduler della
    Fase 10B per ricostruire
    automaticamente i job
    dopo un riavvio del bot.
    """

    async with SessionLocal() as session:
        result = await session.execute(
            select(
                ChannelAutopostConfig,
                ChannelAutopostRuntimeConfig,
                Channel,
                User,
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
            .outerjoin(
                ChannelAutopostRuntimeConfig,
                ChannelAutopostRuntimeConfig
                .channel_id
                == Channel.id,
            )
            .where(
                ChannelAutopostConfig
                .is_enabled
                .is_(True),
                Channel.is_active
                .is_(True),
            )
        )

        rows = result.all()

        enabled: list[
            EnabledAutopostChannel
        ] = []

        for (
            autopost_config,
            runtime_config,
            channel,
            user,
        ) in rows:
            if runtime_config is None:
                runtime_config = (
                    ChannelAutopostRuntimeConfig(
                        channel_id=channel.id
                    )
                )

                session.add(
                    runtime_config
                )

                await session.flush()

            enabled.append(
                EnabledAutopostChannel(
                    owner_telegram_user_id=(
                        user.telegram_user_id
                    ),
                    channel_id=(
                        channel.id
                    ),
                    channel_title=(
                        channel.title
                    ),
                    scan_interval_minutes=int(
                        runtime_config
                        .scan_interval_minutes
                    ),
                    publish_interval_minutes=int(
                        runtime_config
                        .publish_interval_minutes
                    ),
                    max_candidates_per_scan=int(
                        runtime_config
                        .max_candidates_per_scan
                    ),
                )
            )

        await session.commit()

        return enabled
