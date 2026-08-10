import asyncio
import json
import logging
from datetime import (
    datetime,
    timedelta,
    timezone,
)

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from apscheduler.schedulers import (
    SchedulerNotRunningError,
)
from apscheduler.schedulers.asyncio import (
    AsyncIOScheduler,
)

from app.amazon.models import (
    ProductSnapshot,
)
from app.publisher import (
    send_product_post,
)
from app.scheduled_store import (
    STATUS_PENDING,
    get_scheduled_delivery,
    list_pending_scheduled_posts,
    mark_scheduled_failed,
    mark_scheduled_published,
)
from app.template_engine import (
    get_public_url,
)


_scheduler: (
    AsyncIOScheduler | None
) = None

_bot: Bot | None = None


def normalize_utc(
    value: datetime,
) -> datetime:
    """
    SQLite può restituire datetime
    senza tzinfo.

    Nel DB gli orari dello scheduler
    sono sempre interpretati come UTC.
    """

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def scheduled_post_keyboard(
    product: ProductSnapshot,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "Vedi offerta 👀"
                    ),
                    url=get_public_url(
                        product
                    ),
                )
            ]
        ]
    )


async def publish_scheduled_post(
    post_id: int,
) -> None:
    """
    Job eseguito da APScheduler.
    """

    if _bot is None:
        logging.error(
            "Scheduler senza Bot: "
            "post %s non eseguito.",
            post_id,
        )

        return

    delivery = (
        await get_scheduled_delivery(
            post_id
        )
    )

    if delivery is None:
        logging.warning(
            "Post programmato %s "
            "non trovato.",
            post_id,
        )

        return

    scheduled_post, channel = (
        delivery
    )

    if (
        scheduled_post.status
        != STATUS_PENDING
    ):
        return

    if not channel.is_active:
        await mark_scheduled_failed(
            post_id,
            "Canale disattivato.",
        )

        return

    try:
        product_data = json.loads(
            scheduled_post.product_json
        )

        product = (
            ProductSnapshot
            .model_validate(
                product_data
            )
        )

        await send_product_post(
            bot=_bot,
            chat_id=(
                channel.telegram_chat_id
            ),
            product=product,
            text=(
                scheduled_post.post_text
            ),
            reply_markup=(
                scheduled_post_keyboard(
                    product
                )
            ),
        )

        await mark_scheduled_published(
            post_id
        )

        logging.info(
            "Post programmato %s "
            "pubblicato.",
            post_id,
        )

    except Exception as exc:
        logging.exception(
            "Errore pubblicazione "
            "post programmato %s.",
            post_id,
        )

        await mark_scheduled_failed(
            post_id,
            str(exc),
        )


def schedule_post_job(
    post_id: int,
    run_at: datetime,
) -> None:
    """
    Inserisce un post nella coda
    APScheduler.

    Il DB rimane comunque la
    fonte dati principale.
    """

    if _scheduler is None:
        raise RuntimeError(
            "Scheduler non avviato."
        )

    run_date = normalize_utc(
        run_at
    )

    now = datetime.now(
        timezone.utc
    )

    # Se al riavvio troviamo un post
    # che era già scaduto, lo facciamo
    # partire quasi immediatamente.
    if run_date <= now:
        run_date = (
            now
            + timedelta(seconds=2)
        )

    _scheduler.add_job(
        publish_scheduled_post,
        trigger="date",
        run_date=run_date,
        args=[post_id],
        id=(
            f"scheduled_post_{post_id}"
        ),
        replace_existing=True,

        # Se il computer ha avuto
        # un breve ritardo, il job
        # può comunque partire.
        misfire_grace_time=86400,
    )


async def start_scheduler(
    bot: Bot,
) -> None:
    global _scheduler
    global _bot

    if _scheduler is not None:
        return

    _bot = bot

    loop = (
        asyncio.get_running_loop()
    )

    _scheduler = AsyncIOScheduler(
        event_loop=loop,
        timezone=timezone.utc,
    )

    _scheduler.start()

    pending_posts = (
        await list_pending_scheduled_posts()
    )

    for post in pending_posts:
        schedule_post_job(
            post_id=post.id,
            run_at=post.run_at,
        )

    logging.info(
        "Scheduler avviato. "
        "%s post pending ricaricati.",
        len(pending_posts),
    )


def stop_scheduler(
) -> None:
    global _scheduler
    global _bot

    if _scheduler is None:
        return

    try:
        _scheduler.shutdown(
            wait=False
        )

    except SchedulerNotRunningError:
        pass

    _scheduler = None
    _bot = None
