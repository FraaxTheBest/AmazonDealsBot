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
                text="❌ Annulla",
                callback_data="post:cancel",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def preview_keyboard(
    product: ProductSnapshot,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 Apri su Amazon.it",
                    url=product.detail_url,
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
    return (
        "🧪 <b>POST DEMO AmazonDealsBot</b>\n\n"
        f"🔥 <b>{escape(product.title)}</b>\n\n"
        f"❌ Prima: "
        f"{format_money(product.original_price)}\n"
        f"✅ Ora: "
        f"<b>{format_money(product.current_price)}</b>\n"
        f"📉 Sconto: "
        f"<b>{product.discount_percentage or 0}%</b>\n\n"
        f"📦 {escape(product.availability or 'N/D')}\n\n"
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
            "Incolla un URL Amazon.it "
            "oppure direttamente l'ASIN.\n\n"
            "Esempio:\n"
            "<code>"
            "https://www.amazon.it/dp/"
            "B00KL8SM92"
            "</code>"
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
            "❌ Invia un URL Amazon.it "
            "oppure un ASIN."
        )
        return

    asin = await extract_asin(
        message.text
    )

    if asin is None:
        await message.answer(
            "❌ Non riesco a trovare "
            "un ASIN valido.\n\n"
            "Usa un normale link Amazon.it "
            "contenente /dp/ oppure "
            "invia direttamente l'ASIN."
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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Apri offerta",
                    url=product.detail_url,
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
            f"<b>{escape(channel.title)}</b>"
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
            "❌ Creazione post annullata.\n\n"
            "Usa /start per tornare "
            "al menu principale."
        )

    await query.answer()
