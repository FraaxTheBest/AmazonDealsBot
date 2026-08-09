from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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


router = Router(name="posts")

amazon_provider = MockAmazonProvider()


class CreatePostStates(StatesGroup):
    waiting_product = State()


def get_product_url(
    product: ProductSnapshot,
) -> str:
    """
    Sceglie il miglior link disponibile.

    Priorità:
    1. amzn.to affiliato
    2. link affiliato lungo
    3. link normale Amazon
    """

    return (
        getattr(product, "affiliate_short_url", None)
        or getattr(product, "affiliate_url", None)
        or product.detail_url
    )


def channel_selection_keyboard(
    channels: list[Channel],
) -> InlineKeyboardMarkup:
    rows = []

    for channel in channels:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📢 {channel.title[:35]}",
                    callback_data=(
                        f"post:channel:{channel.id}"
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


def product_input_keyboard() -> InlineKeyboardMarkup:
    """Pulsanti della schermata inserimento prodotto."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Indietro",
                    callback_data="post:back_channels",
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
    public_url = get_product_url(product)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Apri su Amazon.it",
                    url=public_url,
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ PUBBLICA",
                    callback_data="post:publish",
                ),
                InlineKeyboardButton(
                    text="❌ SCARTA",
                    callback_data="post:cancel",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Cambia prodotto",
                    callback_data="post:retry_product",
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="menu:home",
                ),
            ],
        ]
    )


def format_money(
    value,
) -> str:
    if value is None:
        return "N/D"

    return (
        f"{value:.2f}"
        .replace(".", ",")
        + " €"
    )


def product_preview(
    product: ProductSnapshot,
) -> str:
    return (
        "🧪 <b>ANTEPRIMA DEMO</b>\n"
        "⚠️ Dati MOCK, non ancora presi "
        "da Amazon.\n\n"
        f"📦 <b>{escape(product.title)}</b>\n\n"
        f"🏷 ASIN: "
        f"<code>{product.asin}</code>\n"
        f"🏭 Brand: "
        f"{escape(product.brand or 'N/D')}\n\n"
        f"❌ Prima: "
        f"{format_money(product.original_price)}\n"
        f"✅ Ora: "
        f"<b>{format_money(product.current_price)}</b>\n"
        f"📉 Sconto: "
        f"{product.discount_percentage or 0}%\n\n"
        f"📦 Disponibilità: "
        f"{escape(product.availability or 'N/D')}"
    )


def channel_post_text(
    product: ProductSnapshot,
) -> str:
    public_url = get_product_url(product)

    rating = getattr(
        product,
        "rating",
        None,
    )

    reviews_count = getattr(
        product,
        "reviews_count",
        None,
    )

    seller = getattr(
        product,
        "seller",
        None,
    )

    ships_from = getattr(
        product,
        "ships_from",
        None,
    )

    rating_text = ""

    if rating is not None:
        rating_text = (
            f"\n⭐ {reviews_count or 0} Recensioni: "
            f"{rating} / 5.0"
        )

    seller_text = ""

    if seller and ships_from:
        seller_text = (
            f"\n📦 Venduto da {escape(seller)} "
            f"e spedito da {escape(ships_from)}"
        )

    return (
        "🧪 <b>POST DEMO AmazonDealsBot</b>\n\n"
        f"👀 <b>{escape(product.title)}</b>\n\n"
        f"💰 A soli "
        f"<b>{format_money(product.current_price)}</b>"
        f" invece di "
        f"{format_money(product.original_price)} "
        f"(-{product.discount_percentage or 0}%)\n\n"
        f"🔎 {public_url}"
        f"{rating_text}"
        f"{seller_text}\n\n"
        "⚠️ Dati demo: provider Amazon "
        "reale non ancora collegato."
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
            f"<b>{escape(channel.title)}</b>\n\n"
            "Puoi inviare:\n\n"
            "• un normale URL Amazon.it\n"
            "• un link corto amzn.to\n"
            "• direttamente l'ASIN\n\n"
            "Esempio:\n"
            "<code>"
            "https://www.amazon.it/dp/"
            "B00KL8SM92"
            "</code>",
            reply_markup=product_input_keyboard(),
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
            "un link amzn.to oppure un ASIN.",
            reply_markup=product_input_keyboard(),
        )
        return

    asin = await extract_asin(
        message.text
    )

    if asin is None:
        await message.answer(
            "❌ Non riesco a trovare "
            "un ASIN valido.\n\n"
            "Puoi utilizzare:\n"
            "• link Amazon.it\n"
            "• link amzn.to\n"
            "• ASIN di 10 caratteri\n\n"
            "Puoi anche tornare indietro.",
            reply_markup=product_input_keyboard(),
        )
        return

    product = await amazon_provider.get_product(
        asin
    )

    await state.update_data(
        product=product.model_dump(
            mode="json"
        )
    )

    await message.answer(
        product_preview(product),
        reply_markup=preview_keyboard(
            product
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
            "🔗 <b>Inserisci prodotto</b>\n\n"
            f"Canale: "
            f"<b>{escape(channel.title)}</b>\n\n"
            "Incolla un nuovo URL Amazon.it, "
            "un link amzn.to oppure l'ASIN.",
            reply_markup=product_input_keyboard(),
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

    product = ProductSnapshot.model_validate(
        product_data
    )

    public_url = get_product_url(
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

    try:
        await bot.send_message(
            chat_id=channel.telegram_chat_id,
            text=channel_post_text(
                product
            ),
            reply_markup=keyboard,
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
            "✅ <b>Post pubblicato!</b>\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Menu principale",
                            callback_data="menu:home",
                        )
                    ]
                ]
            ),
        )

    await query.answer(
        "Pubblicato!",
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
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🏠 Menu principale",
                            callback_data="menu:home",
                        )
                    ]
                ]
            ),
        )

    await query.answer()
