import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from app.autopost_advanced_store import (
    MODE_AUTOMATIC,
    effective_max_posts_per_day,
    event_status,
    failed_attempt_count,
    get_or_create_advanced_config,
    list_publishable_candidates,
    mark_candidate_failed,
    record_publish_attempt,
)
from app.autopost_pipeline import (
    FullAutopostPipelineResult,
    run_channel_autopost_pipeline,
)
from app.autopost_publish_service import (
    AutopostPublishResult,
    publish_approved_candidate,
)
from app.autopost_queue_store import (
    STATUS_APPROVED,
    STATUS_PENDING,
    QueueSaveResult,
    approve_candidate,
    enqueue_autopost_candidates,
)
from app.autopost_ranking import (
    AdvancedRankingResult,
    QueueRankingResult,
    rank_deal_candidates,
    rank_queue_candidates,
)
from app.autopost_runtime_store import (
    get_or_create_runtime_config,
)
from app.autopost_store import (
    get_or_create_autopost_config,
)
from app.autoposting import build_demo_products


_publish_locks: dict[int, asyncio.Lock] = {}


@dataclass(frozen=True, slots=True)
class AdvancedScanResult:
    pipeline: FullAutopostPipelineResult
    ranking: AdvancedRankingResult
    queue: QueueSaveResult
    selected_count: int
    event_active: bool


@dataclass(frozen=True, slots=True)
class LiveRankingSnapshot:
    pipeline: FullAutopostPipelineResult
    ranking: AdvancedRankingResult
    event_active: bool


@dataclass(frozen=True, slots=True)
class AutomaticPublishOutcome:
    status: str
    candidate_id: int | None = None
    publish_result: AutopostPublishResult | None = None
    error_message: str | None = None


def _lock_for_channel(channel_id: int) -> asyncio.Lock:
    lock = _publish_locks.get(channel_id)
    if lock is None:
        lock = asyncio.Lock()
        _publish_locks[channel_id] = lock
    return lock


def _phase11_demo_products():
    """
    Aggiunge metadati esclusivamente ai prodotti DEMO.
    Non inferisce mai tipologie di offerte reali.
    """
    now = datetime.now(timezone.utc)
    products = _phase11_demo_products()
    result = []

    for index, product in enumerate(products):
        updates = {
            "source_updated_at": now - timedelta(minutes=index * 3)
        }

        if product.asin == "B0DEMO0001":
            updates["offer_type"] = "lightning"
        elif product.asin == "B0DEMO0002":
            updates["offer_type"] = "coupon"
        else:
            updates["offer_type"] = "normal"

        result.append(product.model_copy(update=updates))

    return result


async def live_ranking_snapshot(
    owner_telegram_user_id: int,
    channel_id: int,
) -> LiveRankingSnapshot:
    products = build_demo_products()
    pipeline = await run_channel_autopost_pipeline(
        owner_telegram_user_id=owner_telegram_user_id,
        channel_id=channel_id,
        products=products,
    )

    advanced = await get_or_create_advanced_config(
        owner_telegram_user_id,
        channel_id,
    )
    event = event_status(advanced)
    max_posts = effective_max_posts_per_day(advanced)

    ranking = await rank_deal_candidates(
        owner_telegram_user_id,
        channel_id,
        pipeline.final_candidates,
        max_posts_override=max_posts,
    )

    return LiveRankingSnapshot(
        pipeline=pipeline,
        ranking=ranking,
        event_active=event.active,
    )


async def run_advanced_scan(
    owner_telegram_user_id: int,
    channel_id: int,
) -> AdvancedScanResult:
    runtime = await get_or_create_runtime_config(
        owner_telegram_user_id,
        channel_id,
    )

    snapshot = await live_ranking_snapshot(
        owner_telegram_user_id,
        channel_id,
    )

    selected_ranked = snapshot.ranking.ranked[
        : int(runtime.max_candidates_per_scan)
    ]
    selected_candidates = tuple(
        item.candidate
        for item in selected_ranked
    )

    queue_result = await enqueue_autopost_candidates(
        owner_telegram_user_id=owner_telegram_user_id,
        channel_id=channel_id,
        candidates=selected_candidates,
        source="demo",
    )

    return AdvancedScanResult(
        pipeline=snapshot.pipeline,
        ranking=snapshot.ranking,
        queue=queue_result,
        selected_count=len(selected_candidates),
        event_active=snapshot.event_active,
    )


async def automatic_publish_once(
    bot: Bot,
    owner_telegram_user_id: int,
    channel_id: int,
) -> AutomaticPublishOutcome:
    lock = _lock_for_channel(channel_id)

    if lock.locked():
        return AutomaticPublishOutcome(status="busy")

    async with lock:
        autopost = await get_or_create_autopost_config(
            owner_telegram_user_id,
            channel_id,
        )
        if not autopost.is_enabled:
            return AutomaticPublishOutcome(status="disabled")

        advanced = await get_or_create_advanced_config(
            owner_telegram_user_id,
            channel_id,
        )
        if advanced.mode != MODE_AUTOMATIC:
            return AutomaticPublishOutcome(status="approval_mode")

        candidates = await list_publishable_candidates(
            owner_telegram_user_id,
            channel_id,
            limit=200,
        )
        if not candidates:
            return AutomaticPublishOutcome(status="empty")

        max_posts = effective_max_posts_per_day(advanced)
        queue_ranking: QueueRankingResult = await rank_queue_candidates(
            owner_telegram_user_id,
            channel_id,
            candidates,
            max_posts_override=max_posts,
        )

        if not queue_ranking.ranked:
            return AutomaticPublishOutcome(status="no_eligible")

        for ranked in queue_ranking.ranked:
            candidate = ranked.candidate

            attempts = await failed_attempt_count(candidate.id)
            if attempts >= int(advanced.retry_limit):
                await mark_candidate_failed(
                    owner_telegram_user_id,
                    candidate.id,
                )
                continue

            if candidate.status == STATUS_PENDING:
                approved = await approve_candidate(
                    owner_telegram_user_id,
                    candidate.id,
                )
                if approved is None:
                    continue

            elif candidate.status != STATUS_APPROVED:
                continue

            try:
                publish_result = await publish_approved_candidate(
                    bot=bot,
                    owner_telegram_user_id=owner_telegram_user_id,
                    candidate_id=candidate.id,
                )

                await record_publish_attempt(
                    channel_id=channel_id,
                    candidate_id=candidate.id,
                    status="success",
                )

                return AutomaticPublishOutcome(
                    status="published",
                    candidate_id=candidate.id,
                    publish_result=publish_result,
                )

            except Exception as exc:
                error_text = str(exc)[:2000]
                logging.exception(
                    "Pubblicazione automatica fallita | channel=%s | candidate=%s",
                    channel_id,
                    candidate.id,
                )

                await record_publish_attempt(
                    channel_id=channel_id,
                    candidate_id=candidate.id,
                    status="failed",
                    error_message=error_text,
                )

                updated_attempts = await failed_attempt_count(candidate.id)
                if updated_attempts >= int(advanced.retry_limit):
                    await mark_candidate_failed(
                        owner_telegram_user_id,
                        candidate.id,
                    )

                return AutomaticPublishOutcome(
                    status="failed",
                    candidate_id=candidate.id,
                    error_message=error_text,
                )

        return AutomaticPublishOutcome(status="no_eligible")
