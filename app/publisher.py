import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from app.amazon.models import ProductSnapshot


PHOTO_CAPTION_LIMIT = 1024


async def send_product_post(
    bot: Bot,
    chat_id: int,
    product: ProductSnapshot,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> Message:
    """
    Pubblica un prodotto.

    Se esiste image_url:
        FOTO + CAPTION + PULSANTE

    Se l'immagine non esiste o non può
    essere caricata:
        fallback a normale messaggio.
    """

    if (
        product.image_url
        and len(text) <= PHOTO_CAPTION_LIMIT
    ):
        try:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=product.image_url,
                caption=text,
                reply_markup=reply_markup,
            )

        except TelegramAPIError as exc:
            logging.warning(
                "Invio immagine fallito, "
                "uso fallback testuale: %s",
                exc,
            )

    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        link_preview_options=(
            LinkPreviewOptions(
                is_disabled=True
            )
        ),
    )
