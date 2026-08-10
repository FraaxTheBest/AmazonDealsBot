import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.autopost_advanced_store import (
    record_autopost_decision,
)
from app.autopost_queue_store import (
    STATUS_PUBLISHING,
    candidate_product,
    claim_candidate_for_publish,
    get_owner_candidate,
    mark_candidate_published,
    restore_candidate_approved,
)
from app.autopost_ranking import product_offer_type
from app.dedupe_store import record_publication
from app.publisher import send_product_post
from app.template_engine import (
    DEFAULT_POST_TEMPLATE,
    get_public_url,
    render_template,
)
from app.template_store import get_default_template_content


@dataclass(frozen=True, slots=True)
class AutopostPublishResult:
    candidate_id: int
    channel_id: int
    telegram_message_id: int


def product_keyboard(product) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Vedi offerta 👀",
                    url=get_public_url(product),
                )
            ]
        ]
    )


async def publish_approved_candidate(
    bot: Bot,
    owner_telegram_user_id: int,
    candidate_id: int,
) -> AutopostPublishResult:
    claimed = await claim_candidate_for_publish(
        owner_telegram_user_id,
        candidate_id,
    )

    if not claimed:
        raise ValueError(
            "Il candidato non è più disponibile per la pubblicazione."
        )

    sent_to_telegram = False

    try:
        delivery = await get_owner_candidate(
            owner_telegram_user_id,
            candidate_id,
        )
        if delivery is None:
            raise ValueError("Candidato non trovato.")

        candidate, channel = delivery
        if candidate.status != STATUS_PUBLISHING:
            raise ValueError("Stato candidato non valido.")

        product = candidate_product(candidate)
        template = await get_default_template_content(
            owner_telegram_user_id,
            DEFAULT_POST_TEMPLATE,
        )
        text = render_template(template, product)

        message = await send_product_post(
            bot=bot,
            chat_id=channel.telegram_chat_id,
            product=product,
            text=text,
            reply_markup=product_keyboard(product),
        )
        sent_to_telegram = True

        marked = await mark_candidate_published(
            owner_telegram_user_id,
            candidate_id,
        )
        if not marked:
            logging.error(
                "Telegram pubblicato ma candidate %s non marcato published.",
                candidate_id,
            )

        try:
            await record_publication(
                owner_telegram_user_id=owner_telegram_user_id,
                channel_id=channel.id,
                product=product,
                source="autopost",
                telegram_message_id=message.message_id,
            )
        except Exception:
            logging.exception(
                "Pubblicazione riuscita ma dedupe history fallita | candidate=%s",
                candidate_id,
            )

        try:
            await record_autopost_decision(
                owner_telegram_user_id=owner_telegram_user_id,
                candidate=candidate,
                offer_type=product_offer_type(product),
            )
        except Exception:
            logging.exception(
                "Pubblicazione riuscita ma decision history fallita | candidate=%s",
                candidate_id,
            )

        return AutopostPublishResult(
            candidate_id=candidate_id,
            channel_id=channel.id,
            telegram_message_id=message.message_id,
        )

    except Exception:
        # Se Telegram non ha ancora ricevuto il post, possiamo riprovare.
        # Se invece l'invio è avvenuto e il processo fallisce dopo, NON
        # riportiamo APPROVED: il recovery lo gestirà in modo conservativo.
        if not sent_to_telegram:
            await restore_candidate_approved(
                owner_telegram_user_id,
                candidate_id,
            )
        raise
