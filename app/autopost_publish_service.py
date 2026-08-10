import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.autopost_queue_store import (
    STATUS_PUBLISHING,
    candidate_product,
    claim_candidate_for_publish,
    get_owner_candidate,
    mark_candidate_published,
    restore_candidate_approved,
)
from app.dedupe_store import (
    record_publication,
)
from app.publisher import (
    send_product_post,
)
from app.template_engine import (
    DEFAULT_POST_TEMPLATE,
    get_public_url,
    render_template,
)
from app.template_store import (
    get_default_template_content,
)


@dataclass(
    frozen=True,
    slots=True,
)
class AutopostPublishResult:
    candidate_id: int

    channel_id: int

    telegram_message_id: int


def product_keyboard(
    product,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Vedi offerta 👀",
                    url=get_public_url(
                        product
                    ),
                )
            ]
        ]
    )


async def publish_approved_candidate(
    bot: Bot,
    owner_telegram_user_id: int,
    candidate_id: int,
) -> AutopostPublishResult:
    """
    Pubblica un candidato
    precedentemente APPROVATO.
    """

    claimed = (
        await claim_candidate_for_publish(
            owner_telegram_user_id,
            candidate_id,
        )
    )

    if not claimed:
        raise ValueError(
            "Il candidato non è "
            "più disponibile per "
            "la pubblicazione."
        )

    try:
        delivery = (
            await get_owner_candidate(
                owner_telegram_user_id,
                candidate_id,
            )
        )

        if delivery is None:
            raise ValueError(
                "Candidato non trovato."
            )

        candidate, channel = (
            delivery
        )

        if (
            candidate.status
            != STATUS_PUBLISHING
        ):
            raise ValueError(
                "Stato candidato "
                "non valido."
            )

        product = candidate_product(
            candidate
        )

        template = (
            await get_default_template_content(
                owner_telegram_user_id,
                DEFAULT_POST_TEMPLATE,
            )
        )

        text = render_template(
            template,
            product,
        )

        message = await send_product_post(
            bot=bot,
            chat_id=(
                channel.telegram_chat_id
            ),
            product=product,
            text=text,
            reply_markup=(
                product_keyboard(
                    product
                )
            ),
        )

        #
        # Prima segniamo il candidato
        # come pubblicato.
        #
        # Così, anche se lo storico
        # anti-duplicati avesse un
        # problema, non rischiamo un
        # secondo invio premendo
        # nuovamente il pulsante.
        #
        marked = (
            await mark_candidate_published(
                owner_telegram_user_id,
                candidate_id,
            )
        )

        if not marked:
            logging.error(
                (
                    "Messaggio Telegram "
                    "pubblicato ma candidato "
                    "%s non marcato published."
                ),
                candidate_id,
            )

        try:
            await record_publication(
                owner_telegram_user_id=(
                    owner_telegram_user_id
                ),
                channel_id=channel.id,
                product=product,
                source="autopost",
                telegram_message_id=(
                    message.message_id
                ),
            )

        except Exception:
            #
            # Il post ormai è realmente
            # nel canale, quindi NON lo
            # rimettiamo in approved.
            #
            logging.exception(
                (
                    "Pubblicazione riuscita "
                    "ma registrazione "
                    "anti-duplicati fallita "
                    "per candidato %s."
                ),
                candidate_id,
            )

        return AutopostPublishResult(
            candidate_id=(
                candidate_id
            ),
            channel_id=(
                channel.id
            ),
            telegram_message_id=(
                message.message_id
            ),
        )

    except Exception:
        #
        # Se Telegram non ha pubblicato
        # correttamente, ritorniamo ad
        # APPROVED così puoi riprovare.
        #
        await restore_candidate_approved(
            owner_telegram_user_id,
            candidate_id,
        )

        raise
