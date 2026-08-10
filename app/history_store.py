from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.autopost_queue_store import AutopostCandidate, STATUS_FAILED, STATUS_REJECTED
from app.database import Channel, SessionLocal, User
from app.dedupe_store import PublicationEvent


@dataclass(frozen=True, slots=True)
class HistoryItem:
    kind: str
    title: str
    asin: str
    channel_title: str
    at: datetime
    source: str


async def list_history(owner_telegram_user_id: int, limit: int = 30) -> list[HistoryItem]:
    safe = max(1, min(int(limit), 100))
    items: list[HistoryItem] = []
    async with SessionLocal() as session:
        pubs = await session.execute(
            select(PublicationEvent, Channel)
            .join(Channel, PublicationEvent.channel_id == Channel.id)
            .join(User, Channel.owner_id == User.id)
            .where(User.telegram_user_id == owner_telegram_user_id)
            .order_by(PublicationEvent.published_at.desc())
            .limit(safe)
        )
        for event, channel in pubs.all():
            items.append(HistoryItem(
                "published", event.title or event.asin, event.asin,
                channel.title, event.published_at, event.source,
            ))

        rejected = await session.execute(
            select(AutopostCandidate, Channel)
            .join(Channel, AutopostCandidate.channel_id == Channel.id)
            .join(User, AutopostCandidate.owner_id == User.id)
            .where(
                User.telegram_user_id == owner_telegram_user_id,
                AutopostCandidate.status.in_((STATUS_REJECTED, STATUS_FAILED)),
            )
            .order_by(AutopostCandidate.updated_at.desc())
            .limit(safe)
        )
        for candidate, channel in rejected.all():
            items.append(HistoryItem(
                candidate.status, candidate.title, candidate.asin,
                channel.title, candidate.updated_at, candidate.source,
            ))

    def normalized(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    items.sort(key=lambda item: normalized(item.at), reverse=True)
    return items[:safe]
