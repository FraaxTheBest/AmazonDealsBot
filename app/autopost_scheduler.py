import asyncio
import logging
from datetime import timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.autopost_advanced_store import (
    MODE_AUTOMATIC,
    PUBLISH_INTERVAL,
    event_status,
    get_or_create_advanced_config,
    get_publish_slots,
    recover_stale_publishing_for_channel,
)
from app.autopost_auto_service import (
    automatic_publish_once,
    run_advanced_scan,
)
from app.autopost_runtime_store import (
    get_or_create_runtime_config,
    list_enabled_autopost_channels,
)
from app.autopost_store import get_or_create_autopost_config
from app.config import get_settings
from app.analytics_store import record_audit_event, record_autopost_scan
from app.notification_service import notify_admin_error


_scheduler: AsyncIOScheduler | None = None
_bot: Bot | None = None
_job_signatures: dict[int, tuple] = {}


def autopost_scheduler_running() -> bool:
    return _scheduler is not None and bool(getattr(_scheduler, "running", False))


def autopost_job_count() -> int:
    if _scheduler is None:
        return 0
    try:
        return len(_scheduler.get_jobs())
    except Exception:
        return 0


def scan_job_id(channel_id: int) -> str:
    return f"autopost_scan_{channel_id}"


def publish_job_id(channel_id: int) -> str:
    return f"autopost_publish_{channel_id}"


def slot_job_id(channel_id: int, index: int) -> str:
    return f"autopost_slot_{channel_id}_{index}"


def _channel_job_prefixes(channel_id: int) -> tuple[str, ...]:
    return (
        scan_job_id(channel_id),
        publish_job_id(channel_id),
        f"autopost_slot_{channel_id}_",
    )


def _remove_channel_jobs(channel_id: int) -> None:
    if _scheduler is None:
        return

    prefixes = _channel_job_prefixes(channel_id)

    for job in list(_scheduler.get_jobs()):
        if (
            job.id == prefixes[0]
            or job.id == prefixes[1]
            or job.id.startswith(prefixes[2])
        ):
            try:
                _scheduler.remove_job(job.id)
            except JobLookupError:
                pass

    _job_signatures.pop(channel_id, None)


async def run_autopost_scan(
    owner_telegram_user_id: int,
    channel_id: int,
) -> None:
    try:
        config = await get_or_create_autopost_config(
            owner_telegram_user_id,
            channel_id,
        )
        if not config.is_enabled:
            return

        result = await run_advanced_scan(
            owner_telegram_user_id,
            channel_id,
        )

        logging.info(
            (
                "AUTOPOST 11 SCAN | channel=%s | provider=%s | source=%s | "
                "category=%s | filters=%s | deals=%s | dedupe=%s | "
                "advanced_in=%s | blacklist_rejected=%s | "
                "limit_rejected=%s | failed_rejected=%s | "
                "selected=%s | queue_new=%s | queue_refreshed=%s | "
                "pending=%s | event=%s"
            ),
            channel_id,
            result.provider_name,
            result.pipeline.source_count,
            result.pipeline.category_passed_count,
            result.pipeline.filter_passed_count,
            result.pipeline.deal_valid_count,
            result.pipeline.duplicate_count,
            result.ranking.input_count,
            result.ranking.blacklist_rejected_count,
            result.ranking.limit_rejected_count,
            result.ranking.failed_rejected_count,
            result.selected_count,
            result.queue.created_count,
            result.queue.refreshed_count,
            result.queue.pending_total,
            result.event_active,
        )

        try:
            await record_autopost_scan(
                owner_telegram_user_id=owner_telegram_user_id,
                channel_id=channel_id,
                provider=result.provider_name,
                source_count=result.pipeline.source_count,
                category_passed_count=result.pipeline.category_passed_count,
                filter_passed_count=result.pipeline.filter_passed_count,
                deal_valid_count=result.pipeline.deal_valid_count,
                duplicate_count=result.pipeline.duplicate_count,
                blacklist_rejected_count=result.ranking.blacklist_rejected_count,
                limit_rejected_count=result.ranking.limit_rejected_count,
                failed_rejected_count=result.ranking.failed_rejected_count,
                selected_count=result.selected_count,
                queue_new_count=result.queue.created_count,
                event_active=result.event_active,
            )
        except Exception:
            logging.exception("Metriche scansione non registrate | channel=%s", channel_id)

        for index, ranked in enumerate(
            result.ranking.ranked[: result.selected_count],
            start=1,
        ):
            logging.info(
                (
                    "AUTOPOST 11 CANDIDATE | channel=%s | rank=%s | "
                    "asin=%s | base=%s | bonus=%s | final=%s | type=%s"
                ),
                channel_id,
                index,
                ranked.candidate.product.asin,
                ranked.candidate.evaluation.score,
                ranked.priority_bonus,
                ranked.final_score,
                ranked.offer_type,
            )

    except Exception as exc:
        logging.exception(
            "Errore scansione Autopost Fase 11 | channel=%s",
            channel_id,
        )
        try:
            await record_audit_event(
                action="autopost_scan_error",
                owner_telegram_user_id=owner_telegram_user_id,
                channel_id=channel_id,
                level="error",
                details={"error": str(exc)[:500]},
            )
        except Exception:
            pass
        await notify_admin_error(_bot, f"autopost_scan:{channel_id}", f"Scansione Autopost fallita sul canale {channel_id}: {exc}")


async def run_autopost_publish(
    owner_telegram_user_id: int,
    channel_id: int,
) -> None:
    if _bot is None:
        logging.error("Bot non disponibile per autopubblicazione.")
        return

    try:
        outcome = await automatic_publish_once(
            bot=_bot,
            owner_telegram_user_id=owner_telegram_user_id,
            channel_id=channel_id,
        )

        logging.info(
            "AUTOPOST 11 PUBLISH | channel=%s | status=%s | candidate=%s",
            channel_id,
            outcome.status,
            outcome.candidate_id,
        )

    except Exception as exc:
        logging.exception(
            "Errore publisher Autopost Fase 11 | channel=%s",
            channel_id,
        )
        await notify_admin_error(_bot, f"autopost_publish:{channel_id}", f"Publisher Autopost fallito sul canale {channel_id}: {exc}")


async def _channel_signature(
    owner_telegram_user_id: int,
    channel_id: int,
) -> tuple:
    runtime = await get_or_create_runtime_config(
        owner_telegram_user_id,
        channel_id,
    )
    advanced = await get_or_create_advanced_config(
        owner_telegram_user_id,
        channel_id,
    )
    event = event_status(advanced)
    slots = get_publish_slots(advanced)

    scan_interval = (
        event.scan_interval_minutes
        if event.active
        else int(runtime.scan_interval_minutes)
    )
    publish_interval = (
        event.publish_interval_minutes
        if event.active
        else int(runtime.publish_interval_minutes)
    )

    return (
        advanced.mode,
        advanced.publish_strategy,
        tuple(slots),
        event.active,
        event.name,
        int(scan_interval),
        int(publish_interval),
    )


async def register_autopost_channel(
    owner_telegram_user_id: int,
    channel_id: int,
    run_now: bool = True,
) -> None:
    if _scheduler is None:
        return

    runtime = await get_or_create_runtime_config(
        owner_telegram_user_id,
        channel_id,
    )
    advanced = await get_or_create_advanced_config(
        owner_telegram_user_id,
        channel_id,
    )
    event = event_status(advanced)

    _remove_channel_jobs(channel_id)

    scan_interval = (
        int(event.scan_interval_minutes)
        if event.active and event.scan_interval_minutes is not None
        else int(runtime.scan_interval_minutes)
    )

    _scheduler.add_job(
        run_autopost_scan,
        trigger="interval",
        minutes=scan_interval,
        args=[owner_telegram_user_id, channel_id],
        id=scan_job_id(channel_id),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    if advanced.mode == MODE_AUTOMATIC:
        if event.active or advanced.publish_strategy == PUBLISH_INTERVAL:
            publish_interval = (
                int(event.publish_interval_minutes)
                if event.active and event.publish_interval_minutes is not None
                else int(runtime.publish_interval_minutes)
            )

            _scheduler.add_job(
                run_autopost_publish,
                trigger="interval",
                minutes=publish_interval,
                args=[owner_telegram_user_id, channel_id],
                id=publish_job_id(channel_id),
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )

        else:
            settings = get_settings()
            tz = ZoneInfo(settings.app_timezone)

            for index, slot in enumerate(get_publish_slots(advanced)):
                hour, minute = [int(part) for part in slot.split(":")]
                _scheduler.add_job(
                    run_autopost_publish,
                    trigger=CronTrigger(
                        hour=hour,
                        minute=minute,
                        timezone=tz,
                    ),
                    args=[owner_telegram_user_id, channel_id],
                    id=slot_job_id(channel_id, index),
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                    misfire_grace_time=300,
                )

    _job_signatures[channel_id] = await _channel_signature(
        owner_telegram_user_id,
        channel_id,
    )

    logging.info(
        (
            "Autopost 11 registrato | channel=%s | mode=%s | "
            "scan=%s min | publish_strategy=%s | event=%s"
        ),
        channel_id,
        advanced.mode,
        scan_interval,
        advanced.publish_strategy,
        event.active,
    )

    if run_now:
        await run_autopost_scan(
            owner_telegram_user_id,
            channel_id,
        )


async def refresh_autopost_channel(
    owner_telegram_user_id: int,
    channel_id: int,
) -> None:
    if _scheduler is None:
        return

    config = await get_or_create_autopost_config(
        owner_telegram_user_id,
        channel_id,
    )

    if not config.is_enabled:
        _remove_channel_jobs(channel_id)
        return

    await register_autopost_channel(
        owner_telegram_user_id,
        channel_id,
        run_now=False,
    )


async def _supervisor_tick() -> None:
    if _scheduler is None:
        return

    try:
        enabled = await list_enabled_autopost_channels()

        for item in enabled:
            advanced = await get_or_create_advanced_config(
                item.owner_telegram_user_id,
                item.channel_id,
            )
            recovered = await recover_stale_publishing_for_channel(
                item.owner_telegram_user_id,
                item.channel_id,
                int(advanced.stale_publish_minutes),
            )
            if recovered:
                logging.warning(
                    "Autopost recovery | channel=%s | recovered=%s",
                    item.channel_id,
                    recovered,
                )
        enabled_ids = {item.channel_id for item in enabled}

        for channel_id in list(_job_signatures):
            if channel_id not in enabled_ids:
                _remove_channel_jobs(channel_id)

        for item in enabled:
            signature = await _channel_signature(
                item.owner_telegram_user_id,
                item.channel_id,
            )

            if _job_signatures.get(item.channel_id) != signature:
                await register_autopost_channel(
                    item.owner_telegram_user_id,
                    item.channel_id,
                    run_now=False,
                )

    except Exception:
        logging.exception("Errore supervisor Autopost Fase 11.")


async def start_autopost_scheduler(bot: Bot) -> None:
    global _scheduler, _bot

    if _scheduler is not None:
        return

    _bot = bot
    loop = asyncio.get_running_loop()
    _scheduler = AsyncIOScheduler(
        event_loop=loop,
        timezone=timezone.utc,
    )
    _scheduler.start()

    enabled_channels = await list_enabled_autopost_channels()

    for channel in enabled_channels:
        advanced = await get_or_create_advanced_config(
            channel.owner_telegram_user_id,
            channel.channel_id,
        )
        recovered = await recover_stale_publishing_for_channel(
            channel.owner_telegram_user_id,
            channel.channel_id,
            int(advanced.stale_publish_minutes),
        )
        if recovered:
            logging.warning(
                "Startup recovery | channel=%s | recovered=%s",
                channel.channel_id,
                recovered,
            )

        await register_autopost_channel(
            channel.owner_telegram_user_id,
            channel.channel_id,
            run_now=True,
        )

    _scheduler.add_job(
        _supervisor_tick,
        trigger="interval",
        minutes=1,
        id="autopost_supervisor",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )

    logging.info(
        "Autopost Scheduler Fase 11 avviato. %s canali attivi.",
        len(enabled_channels),
    )


def stop_autopost_scheduler() -> None:
    global _scheduler, _bot

    if _scheduler is None:
        return

    try:
        _scheduler.shutdown(wait=False)
    except SchedulerNotRunningError:
        pass

    _scheduler = None
    _bot = None
    _job_signatures.clear()
    logging.info("Autopost Scheduler Fase 11 fermato.")
