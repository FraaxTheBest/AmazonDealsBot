import json
from dataclasses import dataclass
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.autopost_queue_store import (
    AutopostCandidate,
    STATUS_APPROVED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PUBLISHING,
    candidate_product,
)
from app.database import (
    Base,
    Channel,
    SessionLocal,
    User,
)


MODE_APPROVAL = "approval"
MODE_AUTOMATIC = "automatic"

RANK_BEST = "best"
RANK_DISCOUNT = "discount"
RANK_RECENT = "recent"

PUBLISH_INTERVAL = "interval"
PUBLISH_SLOTS = "slots"

BLACKLIST_BRAND = "brand"
BLACKLIST_SELLER = "seller"
BLACKLIST_MANUFACTURER = "manufacturer"
BLACKLIST_ASIN = "asin"
BLACKLIST_KEYWORD = "keyword"

SUPPORTED_MODES = {
    MODE_APPROVAL,
    MODE_AUTOMATIC,
}

SUPPORTED_RANKING_MODES = {
    RANK_BEST,
    RANK_DISCOUNT,
    RANK_RECENT,
}

SUPPORTED_PUBLISH_STRATEGIES = {
    PUBLISH_INTERVAL,
    PUBLISH_SLOTS,
}

SUPPORTED_BLACKLIST_KINDS = {
    BLACKLIST_BRAND,
    BLACKLIST_SELLER,
    BLACKLIST_MANUFACTURER,
    BLACKLIST_ASIN,
    BLACKLIST_KEYWORD,
}


class ChannelAutopostAdvancedConfig(Base):
    __tablename__ = (
        "channel_autopost_advanced_configs"
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

    mode: Mapped[str] = mapped_column(
        String(30),
        default=MODE_APPROVAL,
        nullable=False,
    )

    ranking_mode: Mapped[str] = mapped_column(
        String(30),
        default=RANK_BEST,
        nullable=False,
    )

    publish_strategy: Mapped[str] = mapped_column(
        String(30),
        default=PUBLISH_INTERVAL,
        nullable=False,
    )

    publish_slots_json: Mapped[str] = mapped_column(
        Text,
        default="[]",
        nullable=False,
    )

    alternate_categories: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    alternate_brands: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    max_posts_per_day: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_category_per_day: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_brand_per_day: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    priority_lightning: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )

    priority_coupon: Mapped[int] = mapped_column(
        Integer,
        default=20,
        nullable=False,
    )

    priority_lowest: Mapped[int] = mapped_column(
        Integer,
        default=10,
        nullable=False,
    )

    priority_warehouse: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )

    priority_normal: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    event_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    event_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    event_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    event_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    event_scan_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=5,
        nullable=False,
    )

    event_publish_interval_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
        nullable=False,
    )

    event_max_posts_per_day: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    retry_limit: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    stale_publish_minutes: Mapped[int] = mapped_column(
        Integer,
        default=15,
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


class AutopostBlacklistEntry(Base):
    __tablename__ = "autopost_blacklist_entries"

    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "kind",
            "value_normalized",
            name="uq_autopost_blacklist_channel_kind_value",
        ),
    )

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

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"),
        nullable=False,
        index=True,
    )

    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
    )

    value_normalized: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    value_display: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class AutopostPublicationDecision(Base):
    __tablename__ = "autopost_publication_decisions"

    __table_args__ = (
        UniqueConstraint(
            "candidate_id",
            name="uq_autopost_decision_candidate",
        ),
        Index(
            "ix_autopost_decision_channel_date",
            "channel_id",
            "published_at",
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
        index=True,
    )

    candidate_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    asin: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    brand: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    category_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    offer_type: Mapped[str] = mapped_column(
        String(30),
        default="normal",
        nullable=False,
    )

    score: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class AutopostPublishAttempt(Base):
    __tablename__ = "autopost_publish_attempts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"),
        nullable=False,
        index=True,
    )

    candidate_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


@dataclass(frozen=True, slots=True)
class DailyPublicationCounts:
    total: int
    by_brand: dict[str, int]
    by_category: dict[str, int]


@dataclass(frozen=True, slots=True)
class BlacklistSets:
    brands: frozenset[str]
    sellers: frozenset[str]
    manufacturers: frozenset[str]
    asins: frozenset[str]
    keywords: frozenset[str]


@dataclass(frozen=True, slots=True)
class EffectiveEvent:
    active: bool
    name: str | None
    scan_interval_minutes: int | None
    publish_interval_minutes: int | None
    max_posts_per_day: int | None


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(
        value.strip().lower().split()
    )


def normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def parse_slots_json(value: str) -> tuple[str, ...]:
    try:
        raw = json.loads(value or "[]")
    except json.JSONDecodeError:
        return ()

    if not isinstance(raw, list):
        return ()

    slots: list[str] = []

    for item in raw:
        if not isinstance(item, str):
            continue

        try:
            normalized = normalize_slot(item)
        except ValueError:
            continue

        if normalized not in slots:
            slots.append(normalized)

    return tuple(sorted(slots))


def normalize_slot(value: str) -> str:
    parts = value.strip().split(":")

    if len(parts) != 2:
        raise ValueError("Orario non valido. Usa HH:MM.")

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ValueError("Orario non valido. Usa HH:MM.") from exc

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Orario non valido. Usa HH:MM.")

    return f"{hour:02d}:{minute:02d}"


def validate_slots(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []

    for value in values:
        slot = normalize_slot(value)
        if slot not in normalized:
            normalized.append(slot)

    if len(normalized) > 24:
        raise ValueError("Massimo 24 slot di pubblicazione.")

    return tuple(sorted(normalized))


async def _owned_channel(
    session,
    owner_telegram_user_id: int,
    channel_id: int,
) -> tuple[User, Channel] | None:
    result = await session.execute(
        select(User, Channel)
        .join(Channel, Channel.owner_id == User.id)
        .where(
            User.telegram_user_id == owner_telegram_user_id,
            Channel.id == channel_id,
            Channel.is_active.is_(True),
        )
    )

    row = result.first()
    if row is None:
        return None

    return row[0], row[1]


async def get_or_create_advanced_config(
    owner_telegram_user_id: int,
    channel_id: int,
) -> ChannelAutopostAdvancedConfig:
    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )

        if owned is None:
            raise ValueError("Canale non disponibile.")

        result = await session.execute(
            select(ChannelAutopostAdvancedConfig).where(
                ChannelAutopostAdvancedConfig.channel_id == channel_id
            )
        )

        config = result.scalar_one_or_none()

        if config is None:
            config = ChannelAutopostAdvancedConfig(
                channel_id=channel_id
            )
            session.add(config)
            await session.commit()
            await session.refresh(config)

        return config


def validate_config_change(field: str, value) -> None:
    if field == "mode":
        if value not in SUPPORTED_MODES:
            raise ValueError("Modalità Autoposting non valida.")
        return

    if field == "ranking_mode":
        if value not in SUPPORTED_RANKING_MODES:
            raise ValueError("Ordinamento non valido.")
        return

    if field == "publish_strategy":
        if value not in SUPPORTED_PUBLISH_STRATEGIES:
            raise ValueError("Strategia di pubblicazione non valida.")
        return

    if field in {
        "alternate_categories",
        "alternate_brands",
        "event_enabled",
    }:
        if not isinstance(value, bool):
            raise ValueError("Valore booleano non valido.")
        return

    if field in {
        "max_posts_per_day",
        "max_category_per_day",
        "max_brand_per_day",
        "event_max_posts_per_day",
    }:
        if not 0 <= int(value) <= 1000:
            raise ValueError("Il limite deve essere tra 0 e 1000.")
        return

    if field in {
        "priority_lightning",
        "priority_coupon",
        "priority_lowest",
        "priority_warehouse",
        "priority_normal",
    }:
        if not -100 <= int(value) <= 100:
            raise ValueError("La priorità deve essere tra -100 e 100.")
        return

    if field in {
        "event_scan_interval_minutes",
        "event_publish_interval_minutes",
    }:
        if not 1 <= int(value) <= 1440:
            raise ValueError("L'intervallo deve essere tra 1 e 1440 minuti.")
        return

    if field == "retry_limit":
        if not 1 <= int(value) <= 10:
            raise ValueError("I tentativi devono essere tra 1 e 10.")
        return

    if field == "stale_publish_minutes":
        if not 5 <= int(value) <= 1440:
            raise ValueError("Il timeout deve essere tra 5 e 1440 minuti.")
        return

    if field == "event_name":
        if value is not None and len(str(value).strip()) > 120:
            raise ValueError("Nome evento troppo lungo.")
        return

    if field in {"event_start_at", "event_end_at"}:
        if value is not None and not isinstance(value, datetime):
            raise ValueError("Data evento non valida.")
        return

    raise ValueError("Impostazione avanzata non valida.")


async def set_advanced_value(
    owner_telegram_user_id: int,
    channel_id: int,
    field: str,
    value,
) -> ChannelAutopostAdvancedConfig:
    validate_config_change(field, value)

    await get_or_create_advanced_config(
        owner_telegram_user_id,
        channel_id,
    )

    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )

        if owned is None:
            raise ValueError("Canale non disponibile.")

        result = await session.execute(
            select(ChannelAutopostAdvancedConfig).where(
                ChannelAutopostAdvancedConfig.channel_id == channel_id
            )
        )
        config = result.scalar_one()

        if field in {"event_start_at", "event_end_at"}:
            value = normalize_utc(value)

            current_start = normalize_utc(config.event_start_at)
            current_end = normalize_utc(config.event_end_at)

            if field == "event_start_at" and value is not None:
                if current_end is not None and value >= current_end:
                    raise ValueError("L'inizio evento deve precedere la fine.")

            if field == "event_end_at" and value is not None:
                if current_start is not None and value <= current_start:
                    raise ValueError("La fine evento deve seguire l'inizio.")

        if field == "event_name" and value is not None:
            value = str(value).strip() or None

        setattr(config, field, value)
        config.updated_at = datetime.now(timezone.utc)

        await session.commit()
        await session.refresh(config)
        return config


async def set_publish_slots(
    owner_telegram_user_id: int,
    channel_id: int,
    slots: list[str] | tuple[str, ...],
) -> ChannelAutopostAdvancedConfig:
    normalized = validate_slots(slots)

    await get_or_create_advanced_config(
        owner_telegram_user_id,
        channel_id,
    )

    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )
        if owned is None:
            raise ValueError("Canale non disponibile.")

        result = await session.execute(
            select(ChannelAutopostAdvancedConfig).where(
                ChannelAutopostAdvancedConfig.channel_id == channel_id
            )
        )
        config = result.scalar_one()
        config.publish_slots_json = json.dumps(list(normalized))
        config.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(config)
        return config


def get_publish_slots(
    config: ChannelAutopostAdvancedConfig,
) -> tuple[str, ...]:
    return parse_slots_json(config.publish_slots_json)


def event_status(
    config: ChannelAutopostAdvancedConfig,
    now_utc: datetime | None = None,
) -> EffectiveEvent:
    now = normalize_utc(now_utc) or datetime.now(timezone.utc)
    start = normalize_utc(config.event_start_at)
    end = normalize_utc(config.event_end_at)

    active = bool(
        config.event_enabled
        and start is not None
        and end is not None
        and start <= now <= end
    )

    if not active:
        return EffectiveEvent(
            active=False,
            name=config.event_name,
            scan_interval_minutes=None,
            publish_interval_minutes=None,
            max_posts_per_day=None,
        )

    return EffectiveEvent(
        active=True,
        name=config.event_name or "Evento",
        scan_interval_minutes=int(config.event_scan_interval_minutes),
        publish_interval_minutes=int(config.event_publish_interval_minutes),
        max_posts_per_day=int(config.event_max_posts_per_day),
    )


def effective_max_posts_per_day(
    config: ChannelAutopostAdvancedConfig,
    now_utc: datetime | None = None,
) -> int:
    event = event_status(config, now_utc)

    if event.active and event.max_posts_per_day is not None:
        if event.max_posts_per_day > 0:
            return event.max_posts_per_day

    return int(config.max_posts_per_day)


async def add_blacklist_entry(
    owner_telegram_user_id: int,
    channel_id: int,
    kind: str,
    value: str,
) -> AutopostBlacklistEntry:
    if kind not in SUPPORTED_BLACKLIST_KINDS:
        raise ValueError("Tipo blacklist non valido.")

    display = " ".join(value.strip().split())
    normalized = normalize_text(display)

    if not normalized:
        raise ValueError("Valore blacklist vuoto.")

    if len(display) > 255:
        raise ValueError("Valore blacklist troppo lungo.")

    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )
        if owned is None:
            raise ValueError("Canale non disponibile.")

        owner, channel = owned

        result = await session.execute(
            select(AutopostBlacklistEntry).where(
                AutopostBlacklistEntry.channel_id == channel.id,
                AutopostBlacklistEntry.kind == kind,
                AutopostBlacklistEntry.value_normalized == normalized,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        entry = AutopostBlacklistEntry(
            owner_id=owner.id,
            channel_id=channel.id,
            kind=kind,
            value_normalized=normalized,
            value_display=display,
        )
        session.add(entry)
        await session.commit()
        await session.refresh(entry)
        return entry


async def list_blacklist_entries(
    owner_telegram_user_id: int,
    channel_id: int,
) -> list[AutopostBlacklistEntry]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(AutopostBlacklistEntry)
            .join(User, AutopostBlacklistEntry.owner_id == User.id)
            .where(
                User.telegram_user_id == owner_telegram_user_id,
                AutopostBlacklistEntry.channel_id == channel_id,
            )
            .order_by(
                AutopostBlacklistEntry.kind,
                AutopostBlacklistEntry.value_display,
            )
        )
        return list(result.scalars().all())


async def remove_blacklist_entry(
    owner_telegram_user_id: int,
    entry_id: int,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(AutopostBlacklistEntry)
            .join(User, AutopostBlacklistEntry.owner_id == User.id)
            .where(
                AutopostBlacklistEntry.id == entry_id,
                User.telegram_user_id == owner_telegram_user_id,
            )
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return False

        await session.delete(entry)
        await session.commit()
        return True


async def get_blacklist_sets(
    owner_telegram_user_id: int,
    channel_id: int,
) -> BlacklistSets:
    entries = await list_blacklist_entries(
        owner_telegram_user_id,
        channel_id,
    )

    brands = {
        entry.value_normalized
        for entry in entries
        if entry.kind == BLACKLIST_BRAND
    }
    sellers = {
        entry.value_normalized
        for entry in entries
        if entry.kind == BLACKLIST_SELLER
    }
    manufacturers = {
        entry.value_normalized
        for entry in entries
        if entry.kind == BLACKLIST_MANUFACTURER
    }
    asins = {
        entry.value_normalized.upper()
        for entry in entries
        if entry.kind == BLACKLIST_ASIN
    }
    keywords = {
        entry.value_normalized
        for entry in entries
        if entry.kind == BLACKLIST_KEYWORD
    }

    return BlacklistSets(
        brands=frozenset(brands),
        sellers=frozenset(sellers),
        manufacturers=frozenset(manufacturers),
        asins=frozenset(asins),
        keywords=frozenset(keywords),
    )


def local_day_bounds_utc(
    timezone_name: str,
    now_utc: datetime | None = None,
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name)
    now = normalize_utc(now_utc) or datetime.now(timezone.utc)
    local_now = now.astimezone(tz)
    local_start = local_now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    local_end = local_start + timedelta(days=1)
    return (
        local_start.astimezone(timezone.utc),
        local_end.astimezone(timezone.utc),
    )


async def daily_publication_counts(
    owner_telegram_user_id: int,
    channel_id: int,
    timezone_name: str,
    now_utc: datetime | None = None,
) -> DailyPublicationCounts:
    start_utc, end_utc = local_day_bounds_utc(
        timezone_name,
        now_utc,
    )

    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )
        if owned is None:
            raise ValueError("Canale non disponibile.")

        result = await session.execute(
            select(AutopostPublicationDecision).where(
                AutopostPublicationDecision.channel_id == channel_id,
                AutopostPublicationDecision.published_at >= start_utc,
                AutopostPublicationDecision.published_at < end_utc,
            )
        )
        rows = list(result.scalars().all())

    by_brand: dict[str, int] = {}
    by_category: dict[str, int] = {}

    for row in rows:
        brand_key = normalize_text(row.brand)
        if brand_key:
            by_brand[brand_key] = by_brand.get(brand_key, 0) + 1

        category_key = normalize_text(row.category_key)
        if category_key:
            by_category[category_key] = (
                by_category.get(category_key, 0) + 1
            )

    return DailyPublicationCounts(
        total=len(rows),
        by_brand=by_brand,
        by_category=by_category,
    )


async def list_recent_decisions(
    owner_telegram_user_id: int,
    channel_id: int,
    limit: int = 20,
) -> list[AutopostPublicationDecision]:
    safe_limit = max(1, min(int(limit), 100))

    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )
        if owned is None:
            raise ValueError("Canale non disponibile.")

        result = await session.execute(
            select(AutopostPublicationDecision)
            .where(AutopostPublicationDecision.channel_id == channel_id)
            .order_by(AutopostPublicationDecision.published_at.desc())
            .limit(safe_limit)
        )
        return list(result.scalars().all())


async def record_autopost_decision(
    owner_telegram_user_id: int,
    candidate: AutopostCandidate,
    offer_type: str,
) -> AutopostPublicationDecision:
    product = candidate_product(candidate)

    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            candidate.channel_id,
        )
        if owned is None:
            raise ValueError("Canale non disponibile.")

        existing_result = await session.execute(
            select(AutopostPublicationDecision).where(
                AutopostPublicationDecision.candidate_id == candidate.id
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            return existing

        decision = AutopostPublicationDecision(
            channel_id=candidate.channel_id,
            candidate_id=candidate.id,
            asin=candidate.asin,
            brand=product.brand,
            category_key=product.category_key,
            offer_type=offer_type,
            score=candidate.score,
            published_at=datetime.now(timezone.utc),
        )
        session.add(decision)
        await session.commit()
        await session.refresh(decision)
        return decision


async def record_publish_attempt(
    channel_id: int,
    candidate_id: int,
    status: str,
    error_message: str | None = None,
) -> AutopostPublishAttempt:
    async with SessionLocal() as session:
        attempt = AutopostPublishAttempt(
            channel_id=channel_id,
            candidate_id=candidate_id,
            status=status,
            error_message=(
                error_message[:2000]
                if error_message
                else None
            ),
        )
        session.add(attempt)
        await session.commit()
        await session.refresh(attempt)
        return attempt


async def failed_attempt_count(
    candidate_id: int,
) -> int:
    async with SessionLocal() as session:
        result = await session.execute(
            select(func.count())
            .select_from(AutopostPublishAttempt)
            .where(
                AutopostPublishAttempt.candidate_id == candidate_id,
                AutopostPublishAttempt.status == "failed",
            )
        )
        return int(result.scalar_one())


async def list_publishable_candidates(
    owner_telegram_user_id: int,
    channel_id: int,
    limit: int = 100,
) -> list[AutopostCandidate]:
    safe_limit = max(1, min(int(limit), 500))

    async with SessionLocal() as session:
        result = await session.execute(
            select(AutopostCandidate)
            .join(User, AutopostCandidate.owner_id == User.id)
            .where(
                User.telegram_user_id == owner_telegram_user_id,
                AutopostCandidate.channel_id == channel_id,
                AutopostCandidate.status.in_(
                    (STATUS_PENDING, STATUS_APPROVED)
                ),
            )
            .order_by(
                AutopostCandidate.rank.asc(),
                AutopostCandidate.score.desc(),
                AutopostCandidate.updated_at.desc(),
            )
            .limit(safe_limit)
        )
        return list(result.scalars().all())


async def failed_candidate_asins(
    owner_telegram_user_id: int,
    channel_id: int,
) -> frozenset[str]:
    async with SessionLocal() as session:
        result = await session.execute(
            select(AutopostCandidate.asin)
            .join(User, AutopostCandidate.owner_id == User.id)
            .where(
                User.telegram_user_id == owner_telegram_user_id,
                AutopostCandidate.channel_id == channel_id,
                AutopostCandidate.status == STATUS_FAILED,
            )
        )
        return frozenset(
            str(value).strip().upper()
            for value in result.scalars().all()
        )


async def mark_candidate_failed(
    owner_telegram_user_id: int,
    candidate_id: int,
) -> bool:
    async with SessionLocal() as session:
        result = await session.execute(
            select(AutopostCandidate)
            .join(User, AutopostCandidate.owner_id == User.id)
            .where(
                User.telegram_user_id == owner_telegram_user_id,
                AutopostCandidate.id == candidate_id,
            )
        )
        candidate = result.scalar_one_or_none()
        if candidate is None:
            return False

        candidate.status = STATUS_FAILED
        candidate.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return True


async def recover_stale_publishing_for_channel(
    owner_telegram_user_id: int,
    channel_id: int,
    stale_minutes: int,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=max(5, int(stale_minutes))
    )

    async with SessionLocal() as session:
        owned = await _owned_channel(
            session,
            owner_telegram_user_id,
            channel_id,
        )
        if owned is None:
            return 0

        result = await session.execute(
            select(AutopostCandidate).where(
                AutopostCandidate.channel_id == channel_id,
                AutopostCandidate.status == STATUS_PUBLISHING,
                AutopostCandidate.updated_at < cutoff,
            )
        )
        candidates = list(result.scalars().all())

        for candidate in candidates:
            candidate.status = STATUS_FAILED
            candidate.updated_at = datetime.now(timezone.utc)

        if candidates:
            await session.commit()

        return len(candidates)


async def recover_stale_publishing(
    default_stale_minutes: int = 15,
) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(
        minutes=max(5, int(default_stale_minutes))
    )

    async with SessionLocal() as session:
        result = await session.execute(
            select(AutopostCandidate).where(
                AutopostCandidate.status == STATUS_PUBLISHING,
                AutopostCandidate.updated_at < cutoff,
            )
        )
        candidates = list(result.scalars().all())

        for candidate in candidates:
            candidate.status = STATUS_FAILED
            candidate.updated_at = datetime.now(timezone.utc)

        if candidates:
            await session.commit()

        return len(candidates)
