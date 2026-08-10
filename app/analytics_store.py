from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.autopost_advanced_store import (
    AutopostPublicationDecision,
    AutopostPublishAttempt,
)
from app.autopost_queue_store import (
    AutopostCandidate,
    STATUS_APPROVED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_PUBLISHED,
    STATUS_REJECTED,
)
from app.config import get_settings
from app.database import Base, Channel, SessionLocal, User
from app.dedupe_store import PublicationEvent
from app.scheduled_store import (
    ScheduledPost,
    STATUS_FAILED as SCHEDULED_FAILED,
    STATUS_PENDING as SCHEDULED_PENDING,
)


class AutopostScanMetric(Base):
    __tablename__ = "autopost_scan_metrics"
    __table_args__ = (
        Index("ix_autopost_scan_metric_channel_created", "channel_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False, default="demo")

    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filter_passed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deal_valid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blacklist_rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit_rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queue_new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_active: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


class AdminAuditEvent(Base):
    __tablename__ = "admin_audit_events"
    __table_args__ = (
        Index("ix_admin_audit_created", "created_at"),
        Index("ix_admin_audit_channel_created", "channel_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="info")
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )


@dataclass(frozen=True, slots=True)
class RecentPublication:
    title: str
    asin: str
    source: str
    channel_title: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class StatsSnapshot:
    period_label: str
    published_total: int
    published_autopost: int
    published_manual: int
    published_scheduled: int
    scheduled_pending: int
    scans: int
    offers_scanned: int
    deals_valid: int
    duplicates_avoided: int
    blacklist_rejected: int
    limit_rejected: int
    queue_pending: int
    queue_approved: int
    queue_rejected: int
    queue_failed: int
    publish_errors: int
    scheduled_errors: int
    top_categories: tuple[tuple[str, int], ...]
    top_brands: tuple[tuple[str, int], ...]
    recent_publications: tuple[RecentPublication, ...]


def period_start(period: str, now: datetime | None = None) -> tuple[datetime | None, str]:
    now = now or datetime.now(timezone.utc)
    normalized = period.strip().lower()
    if normalized == "today":
        try:
            local_zone = ZoneInfo(get_settings().app_timezone)
        except ZoneInfoNotFoundError:
            local_zone = timezone.utc
        local_now = now.astimezone(local_zone)
        local_start = local_now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        return local_start.astimezone(timezone.utc), "Oggi"
    if normalized == "7d":
        return now - timedelta(days=7), "Ultimi 7 giorni"
    if normalized == "30d":
        return now - timedelta(days=30), "Ultimi 30 giorni"
    return None, "Tutto"


async def _owner(session, telegram_user_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_user_id == telegram_user_id)
    )
    return result.scalar_one_or_none()


async def record_autopost_scan(
    *,
    owner_telegram_user_id: int,
    channel_id: int,
    provider: str,
    source_count: int,
    category_passed_count: int,
    filter_passed_count: int,
    deal_valid_count: int,
    duplicate_count: int,
    blacklist_rejected_count: int,
    limit_rejected_count: int,
    failed_rejected_count: int,
    selected_count: int,
    queue_new_count: int,
    event_active: bool,
) -> None:
    async with SessionLocal() as session:
        owner = await _owner(session, owner_telegram_user_id)
        if owner is None:
            return
        metric = AutopostScanMetric(
            owner_id=owner.id,
            channel_id=channel_id,
            provider=provider[:30] or "unknown",
            source_count=max(0, int(source_count)),
            category_passed_count=max(0, int(category_passed_count)),
            filter_passed_count=max(0, int(filter_passed_count)),
            deal_valid_count=max(0, int(deal_valid_count)),
            duplicate_count=max(0, int(duplicate_count)),
            blacklist_rejected_count=max(0, int(blacklist_rejected_count)),
            limit_rejected_count=max(0, int(limit_rejected_count)),
            failed_rejected_count=max(0, int(failed_rejected_count)),
            selected_count=max(0, int(selected_count)),
            queue_new_count=max(0, int(queue_new_count)),
            event_active=1 if event_active else 0,
        )
        session.add(metric)
        await session.commit()


async def record_audit_event(
    *,
    action: str,
    owner_telegram_user_id: int | None = None,
    channel_id: int | None = None,
    level: str = "info",
    details: dict[str, Any] | None = None,
) -> None:
    async with SessionLocal() as session:
        owner_id = None
        if owner_telegram_user_id is not None:
            owner = await _owner(session, owner_telegram_user_id)
            owner_id = owner.id if owner else None
        event = AdminAuditEvent(
            owner_id=owner_id,
            channel_id=channel_id,
            level=level[:20],
            action=action[:100],
            details_json=json.dumps(details or {}, ensure_ascii=False, default=str),
        )
        session.add(event)
        await session.commit()


def _with_period(statement, column, start: datetime | None):
    if start is None:
        return statement
    return statement.where(column >= start)


def _with_channel(statement, column, channel_id: int | None):
    if channel_id is None:
        return statement
    return statement.where(column == channel_id)


async def get_stats_snapshot(
    owner_telegram_user_id: int,
    *,
    channel_id: int | None = None,
    period: str = "7d",
) -> StatsSnapshot:
    start, label = period_start(period)

    async with SessionLocal() as session:
        owner = await _owner(session, owner_telegram_user_id)
        if owner is None:
            return StatsSnapshot(
                period_label=label,
                published_total=0,
                published_autopost=0,
                published_manual=0,
                published_scheduled=0,
                scheduled_pending=0,
                scans=0,
                offers_scanned=0,
                deals_valid=0,
                duplicates_avoided=0,
                blacklist_rejected=0,
                limit_rejected=0,
                queue_pending=0,
                queue_approved=0,
                queue_rejected=0,
                queue_failed=0,
                publish_errors=0,
                scheduled_errors=0,
                top_categories=(),
                top_brands=(),
                recent_publications=(),
            )

        owned_channel_ids_result = await session.execute(
            select(Channel.id).where(
                Channel.owner_id == owner.id,
                Channel.is_active.is_(True),
            )
        )
        owned_ids = [int(value) for value in owned_channel_ids_result.scalars().all()]
        if channel_id is not None:
            owned_ids = [value for value in owned_ids if value == channel_id]
        if not owned_ids:
            return StatsSnapshot(
                period_label=label,
                published_total=0,
                published_autopost=0,
                published_manual=0,
                published_scheduled=0,
                scheduled_pending=0,
                scans=0,
                offers_scanned=0,
                deals_valid=0,
                duplicates_avoided=0,
                blacklist_rejected=0,
                limit_rejected=0,
                queue_pending=0,
                queue_approved=0,
                queue_rejected=0,
                queue_failed=0,
                publish_errors=0,
                scheduled_errors=0,
                top_categories=(),
                top_brands=(),
                recent_publications=(),
            )

        pub_stmt = select(PublicationEvent).where(
            PublicationEvent.channel_id.in_(owned_ids)
        )
        pub_stmt = _with_period(pub_stmt, PublicationEvent.published_at, start)
        publications = list((await session.execute(pub_stmt)).scalars().all())

        scan_stmt = select(AutopostScanMetric).where(
            AutopostScanMetric.channel_id.in_(owned_ids)
        )
        scan_stmt = _with_period(scan_stmt, AutopostScanMetric.created_at, start)
        scans = list((await session.execute(scan_stmt)).scalars().all())

        queue_stmt = select(AutopostCandidate.status).where(
            AutopostCandidate.owner_id == owner.id,
            AutopostCandidate.channel_id.in_(owned_ids),
        )
        queue_statuses = list((await session.execute(queue_stmt)).scalars().all())

        scheduled_pending_stmt = select(func.count()).select_from(ScheduledPost).where(
            ScheduledPost.owner_id == owner.id,
            ScheduledPost.channel_id.in_(owned_ids),
            ScheduledPost.status == SCHEDULED_PENDING,
        )
        scheduled_pending = int(
            (await session.execute(scheduled_pending_stmt)).scalar_one()
        )

        scheduled_error_stmt = select(func.count()).select_from(ScheduledPost).where(
            ScheduledPost.owner_id == owner.id,
            ScheduledPost.channel_id.in_(owned_ids),
            ScheduledPost.status == SCHEDULED_FAILED,
        )
        if start is not None:
            scheduled_error_stmt = scheduled_error_stmt.where(
                ScheduledPost.updated_at >= start
            )
        scheduled_errors = int(
            (await session.execute(scheduled_error_stmt)).scalar_one()
        )

        publish_error_stmt = select(func.count()).select_from(
            AutopostPublishAttempt
        ).where(
            AutopostPublishAttempt.channel_id.in_(owned_ids),
            AutopostPublishAttempt.status == "failed",
        )
        if start is not None:
            publish_error_stmt = publish_error_stmt.where(
                AutopostPublishAttempt.created_at >= start
            )
        publish_errors = int(
            (await session.execute(publish_error_stmt)).scalar_one()
        )

        decision_stmt = select(AutopostPublicationDecision).where(
            AutopostPublicationDecision.channel_id.in_(owned_ids)
        )
        if start is not None:
            decision_stmt = decision_stmt.where(
                AutopostPublicationDecision.published_at >= start
            )
        decisions = list((await session.execute(decision_stmt)).scalars().all())

        channel_rows = await session.execute(
            select(Channel.id, Channel.title).where(Channel.id.in_(owned_ids))
        )
        channel_names = {int(row[0]): row[1] for row in channel_rows.all()}

    category_counts: dict[str, int] = {}
    brand_counts: dict[str, int] = {}
    for decision in decisions:
        if decision.category_key:
            category_counts[decision.category_key] = (
                category_counts.get(decision.category_key, 0) + 1
            )
        if decision.brand:
            brand_counts[decision.brand] = brand_counts.get(decision.brand, 0) + 1

    top_categories = tuple(
        sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    )
    top_brands = tuple(
        sorted(brand_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    )

    recent = tuple(
        RecentPublication(
            title=event.title or event.asin,
            asin=event.asin,
            source=event.source,
            channel_title=channel_names.get(event.channel_id, f"Canale {event.channel_id}"),
            published_at=event.published_at,
        )
        for event in sorted(
            publications,
            key=lambda row: row.published_at,
            reverse=True,
        )[:10]
    )

    return StatsSnapshot(
        period_label=label,
        published_total=len(publications),
        published_autopost=sum(1 for row in publications if row.source == "autopost"),
        published_manual=sum(1 for row in publications if row.source in {"manual", "draft", "multi"}),
        published_scheduled=sum(1 for row in publications if row.source == "scheduled"),
        scheduled_pending=scheduled_pending,
        scans=len(scans),
        offers_scanned=sum(row.source_count for row in scans),
        deals_valid=sum(row.deal_valid_count for row in scans),
        duplicates_avoided=sum(row.duplicate_count for row in scans),
        blacklist_rejected=sum(row.blacklist_rejected_count for row in scans),
        limit_rejected=sum(row.limit_rejected_count for row in scans),
        queue_pending=queue_statuses.count(STATUS_PENDING),
        queue_approved=queue_statuses.count(STATUS_APPROVED),
        queue_rejected=queue_statuses.count(STATUS_REJECTED),
        queue_failed=queue_statuses.count(STATUS_FAILED),
        publish_errors=publish_errors,
        scheduled_errors=scheduled_errors,
        top_categories=top_categories,
        top_brands=top_brands,
        recent_publications=recent,
    )


async def scan_diagnostics(
    owner_telegram_user_id: int,
    *,
    channel_id: int | None = None,
    period: str = "7d",
) -> dict[str, int]:
    snapshot = await get_stats_snapshot(
        owner_telegram_user_id,
        channel_id=channel_id,
        period=period,
    )
    return {
        "scans": snapshot.scans,
        "source": snapshot.offers_scanned,
        "deals": snapshot.deals_valid,
        "duplicates": snapshot.duplicates_avoided,
        "blacklist": snapshot.blacklist_rejected,
        "limits": snapshot.limit_rejected,
        "published": snapshot.published_total,
        "errors": snapshot.publish_errors + snapshot.scheduled_errors,
    }
