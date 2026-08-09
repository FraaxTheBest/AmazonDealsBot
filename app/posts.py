from html import escape
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from app.amazon.models import ProductSnapshot
from app.amazon.provider import MockAmazonProvider
from app.amazon.utils import extract_asin
from app.config import get_settings
from app.database import (
    Channel,
    get_channel,
    list_channels,
)
from app.template_engine import (
    get_public_url,
    render_post,
)


router = Router(name="posts")

amazon_provider = MockAmazonProvider()


class CreatePostStates(StatesGroup):
    waiting_product = State()


def is_amzn_short_url(
    value: str,
) -> bool:
    """
    Controlla se il testo inserito
    è un link corto ufficiale amzn.to.
    """

    try:
        parsed = urlparse(
            value.strip()
        )

    except ValueError:
        return False

    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    return (
        parsed.scheme in {"http", "https"}
        and hostname
        in {"amzn.to", "www.amzn.to"}
    )


def channel_selection_keyboard(
    channels: list[Channel],
) -> InlineKeyboardMarkup:
    rows = []

    for channel in channels:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"📢 "
                        f"{channel.title[:35]}"
                    ),
                    callback_data=(
                        f"post:channel:"
                        f"{channel.id}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 Menu principale",
                callback_data="menu:home",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def product_input_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Indietro",
                    callback_data=(
                        "post:back_channels"
                    ),
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="menu:home",
                ),
            ]
        ]
    )


def preview_keyboard(
    product: ProductSnapshot,
) -> InlineKeyboardMarkup:
    public_url = get_public_url(
        product
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Vedi offerta 👀",
                    url=public_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ PUBBLICA",
                    callback_data=(
                        "post:publish"
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ SCARTA",
                    callback_data=(
                        "post:cancel"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Cambia prodotto",
                    callback_data=(
                        "post:retry_product"
                    ),
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="menu:home",
                ),
            ],
        ]
    )


def product_preview(
    product: ProductSnapshot,
) -> str:
    return (
        "🧪 <b>ANTEPRIMA TEMPLATE</b>\n"
        "⚠️ I dati prodotto sono ancora "
        "MOCK.\n\n"
        "────────────────\n\n"
        f"{render_post(product)}"
    )


@router.callback_query(
    F.data == "menu:create_post"
)
async def create_post_start(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    await state.clear()

    channels = await list_channels(
        settings.admin_user_id
    )

    if not channels:
        await query.answer(
            "Prima devi collegare almeno "
            "un canale.",
            show_alert=True,
        )
        return

    if query.message is not None:
        await query.message.edit_text(
            "➕ <b>Crea Post</b>\n\n"
            "Scegli il canale in cui "
            "pubblicare:",
            reply_markup=(
                channel_selection_keyboard(
                    channels
                )
            ),
        )

    await query.answer()


@router.callback_query(
    F.data.startswith("post:channel:")
)
async def select_post_channel(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    if query.data is None:
        return

    channel_id = int(
        query.data.split(":")[-1]
    )

    channel = await get_channel(
        channel_id,
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )
        return

    await state.update_data(
        channel_id=channel.id
    )

    await state.set_state(
        CreatePostStates.waiting_product
    )

    if query.message is not None:
        await query.message.edit_text(
            "🔗 <b>Inserisci prodotto</b>\n\n"
            f"Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Puoi inviare:\n\n"
            "• URL Amazon.it\n"
            "• link corto amzn.to\n"
            "• direttamente l'ASIN\n\n"
            "Se inserisci un link "
            "<b>amzn.to</b>, il bot "
            "manterrà quel link corto "
            "nel post.",
            reply_markup=(
                product_input_keyboard()
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "post:back_channels"
)
async def back_to_channel_selection(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    await state.clear()

    channels = await list_channels(
        settings.admin_user_id
    )

    if query.message is not None:
        await query.message.edit_text(
            "➕ <b>Crea Post</b>\n\n"
            "Scegli il canale in cui "
            "pubblicare:",
            reply_markup=(
                channel_selection_keyboard(
                    channels
                )
            ),
        )

    await query.answer()


@router.message(
    CreatePostStates.waiting_product
)
async def receive_product(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.text:
        await message.answer(
            "❌ Invia un URL Amazon.it, "
            "un link amzn.to oppure "
            "un ASIN.",
            reply_markup=(
                product_input_keyboard()
            ),
        )
        return

    submitted_value = (
        message.text.strip()
    )

    asin = await extract_asin(
        submitted_value
    )

    if asin is None:
        await message.answer(
            "❌ Non riesco a trovare "
            "un ASIN valido.\n\n"
            "Puoi utilizzare:\n"
            "• link Amazon.it\n"
            "• link amzn.to\n"
            "• ASIN di 10 caratteri",
            reply_markup=(
                product_input_keyboard()
            ),
        )
        return

    product = (
        await amazon_provider.get_product(
            asin
        )
    )

    # Se l'utente ha inserito un vero
    # amzn.to, conserviamo proprio quello.
    if is_amzn_short_url(
        submitted_value
    ):
        product = product.model_copy(
            update={
                "affiliate_short_url":
                    submitted_value
            }
        )

    await state.update_data(
        product=product.model_dump(
            mode="json"
        )
    )

    await message.answer(
        product_preview(product),
        reply_markup=(
            preview_keyboard(product)
        ),
        link_preview_options=(
            LinkPreviewOptions(
                is_disabled=True
            )
        ),
    )


@router.callback_query(
    F.data == "post:retry_product"
)
async def retry_product(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    data = await state.get_data()

    channel_id = data.get(
        "channel_id"
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )
        return

    settings = get_settings()

    channel = await get_channel(
        int(channel_id),
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )
        return

    await state.update_data(
        product=None
    )

    await state.set_state(
        CreatePostStates.waiting_product
    )

    if query.message is not None:
        await query.message.edit_text(
            "🔗 <b>Inserisci prodotto</b>"
            "\n\n"
            f"Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Incolla un nuovo URL "
            "Amazon.it, un link amzn.to "
            "oppure l'ASIN.",
            reply_markup=(
                product_input_keyboard()
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "post:publish"
)
async def publish_post(
    query: CallbackQuery,
    bot: Bot,
    state: FSMContext,
) -> None:
    settings = get_settings()

    data = await state.get_data()

    channel_id = data.get(
        "channel_id"
    )

    product_data = data.get(
        "product"
    )

    if (
        channel_id is None
        or product_data is None
    ):
        await query.answer(
            "Sessione scaduta. "
            "Ricomincia da Crea Post.",
            show_alert=True,
        )

        await state.clear()
        return

    channel = await get_channel(
        int(channel_id),
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )
        return

    product = (
        ProductSnapshot.model_validate(
            product_data
        )
    )

    public_url = get_public_url(
        product
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Vedi offerta 👀",
                    url=public_url,
                )
            ]
        ]
    )

    post_text = (
        render_post(product)
        + "\n\n"
        "⚠️ <i>Dati demo: provider "
        "Amazon reale non ancora "
        "collegato.</i>"
    )

    try:
        await bot.send_message(
            chat_id=(
                channel.telegram_chat_id
            ),
            text=post_text,
            reply_markup=keyboard,

            # Niente riquadro/anteprima
            # automatica del link Amazon.
            link_preview_options=(
                LinkPreviewOptions(
                    is_disabled=True
                )
            ),
        )

    except TelegramAPIError:
        await query.answer(
            "❌ Pubblicazione fallita.",
            show_alert=True,
        )
        return

    await state.clear()

    if query.message is not None:
        await query.message.edit_text(
            "✅ <b>Post pubblicato!</b>"
            "\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>",
            reply_markup=(
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=(
                                    "🏠 Menu "
                                    "principale"
                                ),
                                callback_data=(
                                    "menu:home"
                                ),
                            )
                        ]
                    ]
                )
            ),
        )

    await query.answer(
        "Pubblicato!"
    )


@router.callback_query(
    F.data == "post:cancel"
)
async def cancel_post(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if query.message is not None:
        await query.message.edit_text(
            "❌ Creazione post annullata.",
            reply_markup=(
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=(
                                    "🏠 Menu "
                                    "principale"
                                ),
                                callback_data=(
                                    "menu:home"
                                ),
                            )
                        ]
                    ]
                )
            ),
        )

    await query.answer()
