import json
from dataclasses import dataclass
from datetime import (
    datetime,
    timezone,
)
from decimal import Decimal
from typing import Iterable

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
)

from app.amazon.models import (
    ProductSnapshot,
)
from app.database import (
    Base,
    Channel,
    SessionLocal,
    User,
)
from app.deal_pipeline import (
    DealCandidate,
)


# =========================================================
# STATUS
# =========================================================


STATUS_PENDING = "pending"

STATUS_APPROVED = "approved"

STATUS_REJECTED = "rejected"

STATUS_PUBLISHED = "published"

STATUS_FAILED = "failed"


ACTIVE_STATUSES = (
    STATUS_PENDING,
    STATUS_APPROVED,
)


# =========================================================
# MODELLO DATABASE
# =========================================================


class AutopostCandidate(
    Base
):
    """
    Prodotto trovato automaticamente
    e inserito nella coda Autopost.

    La tabella contiene uno snapshot
    completo del prodotto al momento
    della scansione.
    """

    __tablename__ = (
        "autopost_candidates"
    )

    __table_args__ = (
        Index(
            "ix_autopost_candidate_"
            "channel_status",
            "channel_id",
            "status",
        ),
        Index(
            "ix_autopost_candidate_"
            "channel_asin",
            "channel_id",
            "asin",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    owner_id: Mapped[int] = (
        mapped_column(
            ForeignKey("users.id"),
            nullable=False,
            index=True,
        )
    )

    channel_id: Mapped[int] = (
        mapped_column(
            ForeignKey("channels.id"),
            nullable=False,
            index=True,
        )
    )

    asin: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    product_json: Mapped[str] = (
        mapped_column(
            Text,
            nullable=False,
        )
    )

    current_price: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    original_price: Mapped[
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

    savings_amount: Mapped[
        Decimal | None
    ] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    score: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
        )
    )

    verdict: Mapped[str] = (
        mapped_column(
            String(50),
            nullable=False,
        )
    )

    rank: Mapped[int] = (
        mapped_column(
            Integer,
            nullable=False,
        )
    )

    source: Mapped[str] = (
        mapped_column(
            String(30),
            default="demo",
            nullable=False,
        )
    )

    status: Mapped[str] = (
        mapped_column(
            String(30),
            default=STATUS_PENDING,
            nullable=False,
            index=True,
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

    last_seen_at: Mapped[
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

    decided_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    published_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# =========================================================
# RISULTATO INSERIMENTO
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class QueueSaveResult:
    selected_count: int

    created_count: int

    refreshed_count: int

    skipped_active_count: int

    pending_total: int


# =========================================================
# HELPERS
# =========================================================


def normalize_asin(
    asin: str,
) -> str:
    return (
        asin.strip().upper()
    )


def serialize_product(
    product: ProductSnapshot,
) -> str:
    return json.dumps(
        product.model_dump(
            mode="json"
        ),
        ensure_ascii=False,
    )


def candidate_product(
    candidate: AutopostCandidate,
) -> ProductSnapshot:
    data = json.loads(
        candidate.product_json
    )

    return (
        ProductSnapshot
        .model_validate(
            data
        )
    )


async def _get_owner_channel(
    session,
    owner_telegram_user_id: int,
    channel_id: int,
) -> tuple[
    User,
    Channel,
] | None:
    result = await session.execute(
        select(
            User,
            Channel,
        )
        .join(
            Channel,
            Channel.owner_id
            == User.id,
        )
        .where(
            User.telegram_user_id
            == owner_telegram_user_id,
            Channel.id
            == channel_id,
            Channel.is_active
            .is_(True),
        )
    )

    row = result.first()

    if row is None:
        return None

    return (
        row[0],
        row[1],
    )


# =========================================================
# SALVA CANDIDATI
# =========================================================


async def enqueue_autopost_candidates(
    owner_telegram_user_id: int,
    channel_id: int,
    candidates: Iterable[
        DealCandidate
    ],
    source: str = "demo",
) -> QueueSaveResult:
    """
    Inserisce i candidati nella coda.

    Regole:

    - nuovo ASIN -> crea PENDING
    - ASIN già PENDING -> aggiorna snapshot
    - ASIN APPROVED -> non duplica
    """

    raw_candidates = tuple(
        candidates
    )

    # =====================================================
    # RIMUOVI DUPLICATI NELLO STESSO BATCH
    # =====================================================

    selected: list[
        DealCandidate
    ] = []

    seen_asins: set[str] = set()

    for candidate in raw_candidates:
        asin = normalize_asin(
            candidate.product.asin
        )

        if not asin:
            continue

        if asin in seen_asins:
            continue

        seen_asins.add(
            asin
        )

        selected.append(
            candidate
        )

    normalized_source = (
        source.strip().lower()[:30]
        or "unknown"
    )

    now = datetime.now(
        timezone.utc
    )

    async with SessionLocal() as session:
        owner_channel = (
            await _get_owner_channel(
                session,
                owner_telegram_user_id,
                channel_id,
            )
        )

        if owner_channel is None:
            raise ValueError(
                "Canale non disponibile."
            )

        owner, channel = (
            owner_channel
        )

        asins = [
            normalize_asin(
                candidate.product.asin
            )
            for candidate in selected
        ]

        existing_by_asin: dict[
            str,
            AutopostCandidate,
        ] = {}

        if asins:
            existing_result = (
                await session.execute(
                    select(
                        AutopostCandidate
                    )
                    .where(
                        AutopostCandidate
                        .channel_id
                        == channel.id,
                        AutopostCandidate
                        .asin
                        .in_(asins),
                        AutopostCandidate
                        .status
                        .in_(
                            ACTIVE_STATUSES
                        ),
                    )
                    .order_by(
                        AutopostCandidate
                        .id.desc()
                    )
                )
            )

            for existing in (
                existing_result
                .scalars()
                .all()
            ):
                if (
                    existing.asin
                    not in existing_by_asin
                ):
                    existing_by_asin[
                        existing.asin
                    ] = existing

        created_count = 0

        refreshed_count = 0

        skipped_active_count = 0

        for rank, deal_candidate in enumerate(
            selected,
            start=1,
        ):
            product = (
                deal_candidate.product
            )

            evaluation = (
                deal_candidate.evaluation
            )

            asin = normalize_asin(
                product.asin
            )

            existing = (
                existing_by_asin.get(
                    asin
                )
            )

            # =============================================
            # GIÀ APPROVATO
            #
            # Non modifichiamo un prodotto
            # già approvato dall'admin.
            # =============================================

            if (
                existing is not None
                and existing.status
                == STATUS_APPROVED
            ):
                skipped_active_count += 1

                continue

            # =============================================
            # GIÀ PENDING
            #
            # Aggiorniamo il prodotto invece
            # di creare un duplicato.
            # =============================================

            if existing is not None:
                existing.title = (
                    product.title
                )

                existing.product_json = (
                    serialize_product(
                        product
                    )
                )

                existing.current_price = (
                    product.current_price
                )

                existing.original_price = (
                    product.original_price
                )

                existing.discount_percentage = (
                    evaluation
                    .discount_percentage
                )

                existing.savings_amount = (
                    evaluation
                    .savings_amount
                )

                existing.score = (
                    evaluation.score
                )

                existing.verdict = (
                    evaluation.verdict
                )

                existing.rank = rank

                existing.source = (
                    normalized_source
                )

                existing.last_seen_at = now

                existing.updated_at = now

                refreshed_count += 1

                continue

            # =============================================
            # NUOVO CANDIDATO
            # =============================================

            queue_candidate = (
                AutopostCandidate(
                    owner_id=owner.id,
                    channel_id=channel.id,
                    asin=asin,
                    title=product.title,
                    product_json=(
                        serialize_product(
                            product
                        )
                    ),
                    current_price=(
                        product.current_price
                    ),
                    original_price=(
                        product.original_price
                    ),
                    discount_percentage=(
                        evaluation
                        .discount_percentage
                    ),
                    savings_amount=(
                        evaluation
                        .savings_amount
                    ),
                    score=(
                        evaluation.score
                    ),
                    verdict=(
                        evaluation.verdict
                    ),
                    rank=rank,
                    source=(
                        normalized_source
                    ),
                    status=(
                        STATUS_PENDING
                    ),
                    created_at=now,
                    last_seen_at=now,
                    updated_at=now,
                )
            )

            session.add(
                queue_candidate
            )

            existing_by_asin[
                asin
            ] = queue_candidate

            created_count += 1

        await session.flush()

        pending_result = (
            await session.execute(
                select(
                    func.count()
                )
                .select_from(
                    AutopostCandidate
                )
                .where(
                    AutopostCandidate
                    .channel_id
                    == channel.id,
                    AutopostCandidate
                    .status
                    == STATUS_PENDING,
                )
            )
        )

        pending_total = int(
            pending_result.scalar_one()
        )

        await session.commit()

        return QueueSaveResult(
            selected_count=len(
                selected
            ),
            created_count=(
                created_count
            ),
            refreshed_count=(
                refreshed_count
            ),
            skipped_active_count=(
                skipped_active_count
            ),
            pending_total=(
                pending_total
            ),
        )


# =========================================================
# LISTA PENDING
# =========================================================


async def list_owner_pending_candidates(
    owner_telegram_user_id: int,
    channel_id: int | None = None,
    limit: int = 100,
) -> list[
    tuple[
        AutopostCandidate,
        Channel,
    ]
]:
    safe_limit = max(
        1,
        min(
            int(limit),
            500,
        ),
    )

    async with SessionLocal() as session:
        statement = (
            select(
                AutopostCandidate,
                Channel,
            )
            .join(
                Channel,
                AutopostCandidate
                .channel_id
                == Channel.id,
            )
            .join(
                User,
                AutopostCandidate
                .owner_id
                == User.id,
            )
            .where(
                User.telegram_user_id
                == owner_telegram_user_id,
                AutopostCandidate.status
                == STATUS_PENDING,
            )
        )

        if channel_id is not None:
            statement = (
                statement.where(
                    AutopostCandidate
                    .channel_id
                    == channel_id
                )
            )

        result = await session.execute(
            statement
            .order_by(
                AutopostCandidate
                .score.desc(),
                AutopostCandidate
                .created_at.asc(),
            )
            .limit(
                safe_limit
            )
        )

        return [
            (
                row[0],
                row[1],
            )
            for row in result.all()
        ]


# =========================================================
# RECUPERA SINGOLO CANDIDATO
# =========================================================


async def get_owner_candidate(
    owner_telegram_user_id: int,
    candidate_id: int,
) -> tuple[
    AutopostCandidate,
    Channel,
] | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(
                AutopostCandidate,
                Channel,
            )
            .join(
                Channel,
                AutopostCandidate
                .channel_id
                == Channel.id,
            )
            .join(
                User,
                AutopostCandidate
                .owner_id
                == User.id,
            )
            .where(
                AutopostCandidate.id
                == candidate_id,
                User.telegram_user_id
                == owner_telegram_user_id,
            )
        )

        row = result.first()

        if row is None:
            return None

        return (
            row[0],
            row[1],
        )
