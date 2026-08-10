import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ai_service import enhance_product_with_ai
from app.analytics_store import record_audit_event
from app.autopost_advanced_store import mark_candidate_failed, record_autopost_decision
from app.autopost_queue_store import (
    STATUS_PUBLISHING,
    candidate_product,
    claim_candidate_for_publish,
    get_owner_candidate,
    mark_candidate_published,
    restore_candidate_approved,
)
from app.autopost_ranking import product_offer_type
from app.config import get_settings
from app.dedupe_store import record_publication
from app.publisher import send_product_post
from app.shortlink_service import build_offer_url
from app.template_engine import DEFAULT_POST_TEMPLATE, render_template
from app.template_store import get_default_template_content


@dataclass(frozen=True, slots=True)
class AutopostPublishResult:
    candidate_id: int
    channel_id: int
    telegram_message_id: int


def product_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Vedi offerta 👀", url=url)
    ]])


async def _render(owner_id: int, product) -> str:
    template = await get_default_template_content(owner_id, DEFAULT_POST_TEMPLATE)
    try:
        return render_template(template, product)
    except ValueError:
        return render_template(DEFAULT_POST_TEMPLATE, product)


async def publish_approved_candidate(
    bot: Bot,
    owner_telegram_user_id: int,
    candidate_id: int,
) -> AutopostPublishResult:
    claimed = await claim_candidate_for_publish(owner_telegram_user_id, candidate_id)
    if not claimed:
        raise ValueError("Il candidato non è più disponibile per la pubblicazione.")

    sent_to_telegram = False
    try:
        delivery = await get_owner_candidate(owner_telegram_user_id, candidate_id)
        if delivery is None:
            raise ValueError("Candidato non trovato.")
        candidate, channel = delivery
        if candidate.status != STATUS_PUBLISHING:
            raise ValueError("Stato candidato non valido.")

        product = candidate_product(candidate)
        # L'AI è un arricchimento opzionale. Un errore AI non blocca mai il post.
        try:
            ai_result = await enhance_product_with_ai(owner_telegram_user_id, product)
            product = ai_result.product
            if ai_result.error_message:
                logging.warning("AI non usata | candidate=%s | %s", candidate_id, ai_result.error_message)
        except Exception:
            logging.exception("AI enhancement fallito | candidate=%s", candidate_id)

        text = await _render(owner_telegram_user_id, product)
        settings = get_settings()
        if settings.amazon_provider == "demo":
            text += "\n\n⚠️ <i>Dati demo: provider Amazon reale non ancora collegato.</i>"

        try:
            url = await build_offer_url(
                owner_telegram_user_id=owner_telegram_user_id,
                channel_id=channel.id,
                product=product,
            )
        except Exception:
            logging.exception("Shortlink fallito, uso URL Amazon | candidate=%s", candidate_id)
            from app.template_engine import get_public_url
            url = get_public_url(product)

        message = await send_product_post(
            bot=bot,
            chat_id=channel.telegram_chat_id,
            product=product,
            text=text,
            reply_markup=product_keyboard(url),
        )
        sent_to_telegram = True

        # Da questo punto NON torniamo mai ad APPROVED: Telegram ha già ricevuto.
        # Se il normale aggiornamento PUBLISHED fallisce, usiamo FAILED come
        # stato terminale conservativo: è meno elegante, ma impedisce un retry
        # che potrebbe creare un doppione nel canale.
        try:
            marked = await mark_candidate_published(
                owner_telegram_user_id,
                candidate_id,
            )
        except Exception:
            marked = False
            logging.exception(
                "Telegram pubblicato ma aggiornamento PUBLISHED fallito | candidate=%s",
                candidate_id,
            )

        if not marked:
            logging.error(
                "Telegram pubblicato ma candidate %s non marcato published; "
                "imposto stato terminale FAILED per evitare retry.",
                candidate_id,
            )
            try:
                await mark_candidate_failed(
                    owner_telegram_user_id,
                    candidate_id,
                )
            except Exception:
                logging.exception(
                    "Impossibile impostare stato terminale | candidate=%s",
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
            logging.exception("Dedupe history fallita | candidate=%s", candidate_id)

        try:
            await record_autopost_decision(
                owner_telegram_user_id=owner_telegram_user_id,
                candidate=candidate,
                offer_type=product_offer_type(product),
            )
        except Exception:
            logging.exception("Decision history fallita | candidate=%s", candidate_id)

        try:
            await record_audit_event(
                action="autopost_published",
                owner_telegram_user_id=owner_telegram_user_id,
                channel_id=channel.id,
                details={"candidate_id": candidate_id, "asin": product.asin},
            )
        except Exception:
            pass

        return AutopostPublishResult(candidate_id, channel.id, message.message_id)

    except Exception:
        if not sent_to_telegram:
            await restore_candidate_approved(owner_telegram_user_id, candidate_id)
        raise
