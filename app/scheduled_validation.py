from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.amazon.models import ProductSnapshot
from app.database import SessionLocal, User
from app.scheduled_store import ScheduledPost


STATUS_EXPIRED = "expired"
STATUS_SENT_UNCERTAIN = "sent_uncertain"


@dataclass(frozen=True, slots=True)
class ScheduledValidationResult:
    valid: bool
    reason: str | None = None


def _available(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    blocked = ("non disponibile", "unavailable", "esaurito", "out of stock")
    return not any(token in normalized for token in blocked)


def validate_refreshed_product(
    original: ProductSnapshot,
    refreshed: ProductSnapshot,
) -> ScheduledValidationResult:
    if refreshed.current_price is None:
        return ScheduledValidationResult(False, "Prezzo non disponibile al momento della pubblicazione.")
    if not _available(refreshed.availability):
        return ScheduledValidationResult(False, "Prodotto non più disponibile.")

    original_discount = original.discount_percentage
    refreshed_discount = refreshed.discount_percentage
    if original_discount is not None and original_discount >= Decimal("10"):
        if refreshed_discount is None or refreshed_discount < Decimal("5"):
            return ScheduledValidationResult(False, "L'offerta non è più sufficientemente scontata.")

    return ScheduledValidationResult(True)


async def mark_scheduled_expired(post_id: int, reason: str) -> None:
    async with SessionLocal() as session:
        result = await session.execute(select(ScheduledPost).where(ScheduledPost.id == post_id))
        post = result.scalar_one_or_none()
        if post is None:
            return
        post.status = STATUS_EXPIRED
        post.error_message = reason[:2000]
        post.updated_at = datetime.now(timezone.utc)
        await session.commit()


async def mark_scheduled_sent_uncertain(post_id: int, reason: str) -> None:
    """Stato terminale conservativo dopo un invio Telegram riuscito.

    Evita che un problema DB successivo all'invio lasci il post in PENDING
    e quindi lo faccia ripubblicare al prossimo riavvio.
    """
    async with SessionLocal() as session:
        result = await session.execute(
            select(ScheduledPost).where(ScheduledPost.id == post_id)
        )
        post = result.scalar_one_or_none()
        if post is None:
            return
        post.status = STATUS_SENT_UNCERTAIN
        post.error_message = reason[:2000]
        post.updated_at = datetime.now(timezone.utc)
        post.published_at = post.published_at or datetime.now(timezone.utc)
        await session.commit()


async def scheduled_owner_telegram_id(post: ScheduledPost) -> int | None:
    async with SessionLocal() as session:
        result = await session.execute(select(User.telegram_user_id).where(User.id == post.owner_id))
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None
