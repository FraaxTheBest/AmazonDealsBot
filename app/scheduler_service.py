import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.amazon.models import ProductSnapshot
from app.amazon.provider_factory import refresh_product
from app.config import get_settings
from app.dedupe_store import record_publication
from app.notification_service import notify_admin_error
from app.publisher import send_product_post
from app.scheduled_store import (
    STATUS_PENDING,
    get_scheduled_delivery,
    list_pending_scheduled_posts,
    mark_scheduled_failed,
    mark_scheduled_published,
)
from app.scheduled_validation import (
    mark_scheduled_expired,
    mark_scheduled_sent_uncertain,
    scheduled_owner_telegram_id,
    validate_refreshed_product,
)
from app.shortlink_service import build_offer_url
from app.template_engine import DEFAULT_POST_TEMPLATE, render_template
from app.template_store import get_default_template_content


_scheduler: AsyncIOScheduler | None = None
_bot: Bot | None = None


def normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_job_id(post_id: int) -> str:
    return f"scheduled_post_{post_id}"


def scheduler_running() -> bool:
    return _scheduler is not None and bool(getattr(_scheduler, "running", False))


def scheduler_job_count() -> int:
    if _scheduler is None:
        return 0
    try:
        return len(_scheduler.get_jobs())
    except Exception:
        return 0


def scheduled_post_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Vedi offerta 👀", url=url)
    ]])


async def _fresh_text(owner_id: int, product: ProductSnapshot, fallback: str) -> str:
    template = await get_default_template_content(owner_id, DEFAULT_POST_TEMPLATE)
    try:
        return render_template(template, product)
    except Exception:
        try:
            return render_template(DEFAULT_POST_TEMPLATE, product)
        except Exception:
            return fallback


async def publish_scheduled_post(post_id: int) -> None:
    if _bot is None:
        logging.error("Scheduler senza Bot: post %s non eseguito.", post_id)
        return

    delivery = await get_scheduled_delivery(post_id)
    if delivery is None:
        logging.warning("Post programmato %s non trovato.", post_id)
        return

    scheduled_post, channel = delivery
    if scheduled_post.status != STATUS_PENDING:
        return

    if not channel.is_active:
        await mark_scheduled_failed(post_id, "Canale disattivato.")
        return

    owner_id = await scheduled_owner_telegram_id(scheduled_post)
    if owner_id is None:
        await mark_scheduled_failed(post_id, "Proprietario non trovato.")
        return

    sent_to_telegram = False
    refreshed: ProductSnapshot | None = None
    message = None

    try:
        original = ProductSnapshot.model_validate(
            json.loads(scheduled_post.product_json)
        )
        refreshed = await refresh_product(
            original,
            owner_id,
            channel.id,
        )
        validation = validate_refreshed_product(original, refreshed)
        if not validation.valid:
            await mark_scheduled_expired(
                post_id,
                validation.reason or "Offerta non più valida.",
            )
            logging.info(
                "Post programmato %s scaduto: %s",
                post_id,
                validation.reason,
            )
            return

        post_text = await _fresh_text(
            owner_id,
            refreshed,
            scheduled_post.post_text,
        )
        settings = get_settings()
        if settings.amazon_provider == "demo":
            post_text += (
                "\n\n⚠️ <i>Dati demo: provider Amazon reale "
                "non ancora collegato.</i>"
            )

        try:
            url = await build_offer_url(
                owner_telegram_user_id=owner_id,
                channel_id=channel.id,
                product=refreshed,
            )
        except Exception:
            logging.exception(
                "Shortlink non disponibile per post programmato %s.",
                post_id,
            )
            from app.template_engine import get_public_url
            url = get_public_url(refreshed)

        message = await send_product_post(
            bot=_bot,
            chat_id=channel.telegram_chat_id,
            product=refreshed,
            text=post_text,
            reply_markup=scheduled_post_keyboard(url),
        )
        sent_to_telegram = True

    except Exception as exc:
        logging.exception(
            "Errore pubblicazione post programmato %s.",
            post_id,
        )
        if not sent_to_telegram:
            await mark_scheduled_failed(post_id, str(exc))
            await notify_admin_error(
                _bot,
                f"scheduled:{post_id}",
                f"Post programmato #{post_id} fallito: {exc}",
            )
        return

    # Da qui in poi il messaggio è già nel canale.
    # Qualunque errore di persistenza NON deve trasformarsi in un retry,
    # altrimenti potremmo pubblicare lo stesso prodotto due volte.
    try:
        await mark_scheduled_published(post_id)
    except Exception as exc:
        logging.exception(
            "Messaggio Telegram pubblicato ma stato scheduled #%s "
            "non aggiornato.",
            post_id,
        )
        try:
            await mark_scheduled_sent_uncertain(
                post_id,
                f"Telegram inviato ma aggiornamento stato fallito: {exc}",
            )
        except Exception:
            logging.exception(
                "Impossibile impostare sent_uncertain per scheduled #%s.",
                post_id,
            )
        await notify_admin_error(
            _bot,
            f"scheduled-state:{post_id}",
            f"Post programmato #{post_id} inviato su Telegram, "
            "ma lo stato DB non è stato aggiornato normalmente. "
            "Il sistema evita comunque il retry automatico.",
        )

    if refreshed is not None and message is not None:
        try:
            await record_publication(
                owner_telegram_user_id=owner_id,
                channel_id=channel.id,
                product=refreshed,
                source="scheduled",
                telegram_message_id=message.message_id,
            )
        except Exception:
            logging.exception(
                "Storico post programmato %s non registrato.",
                post_id,
            )

    logging.info("Post programmato %s pubblicato.", post_id)


def schedule_post_job(post_id: int, run_at: datetime) -> None:
    if _scheduler is None:
        raise RuntimeError("Scheduler non avviato.")
    run_date = normalize_utc(run_at)
    now = datetime.now(timezone.utc)
    if run_date <= now:
        run_date = now + timedelta(seconds=2)
    _scheduler.add_job(
        publish_scheduled_post,
        trigger="date",
        run_date=run_date,
        args=[post_id],
        id=get_job_id(post_id),
        replace_existing=True,
        misfire_grace_time=86400,
    )


def cancel_post_job(post_id: int) -> None:
    if _scheduler is None:
        return
    try:
        _scheduler.remove_job(get_job_id(post_id))
    except JobLookupError:
        pass


def reschedule_post_job(post_id: int, run_at: datetime) -> None:
    schedule_post_job(post_id=post_id, run_at=run_at)


async def start_scheduler(bot: Bot) -> None:
    global _scheduler, _bot
    if _scheduler is not None:
        return
    _bot = bot
    loop = asyncio.get_running_loop()
    _scheduler = AsyncIOScheduler(event_loop=loop, timezone=timezone.utc)
    _scheduler.start()
    pending_posts = await list_pending_scheduled_posts()
    for post in pending_posts:
        schedule_post_job(post.id, post.run_at)
    logging.info("Scheduler avviato. %s post pending ricaricati.", len(pending_posts))


def stop_scheduler() -> None:
    global _scheduler, _bot
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except SchedulerNotRunningError:
        pass
    _scheduler = None
    _bot = None
