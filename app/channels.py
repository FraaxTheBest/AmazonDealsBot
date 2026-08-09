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
    MessageOriginChannel,
    ChatMemberAdministrator,
)

from app.config import get_settings
from app.database import (
    Channel,
    disable_channel,
    get_channel,
    list_channels,
    save_channel,
)


router = Router(name="channels")


class AddChannelStates(StatesGroup):
    waiting_forward = State()


def channels_keyboard(
    channels: list[Channel],
) -> InlineKeyboardMarkup:
    rows = []

    for channel in channels:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"📢 {channel.title[:35]}",
                    callback_data=f"channel:view:{channel.id}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="➕ Aggiungi canale",
                callback_data="channels:add",
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Menu principale",
                callback_data="menu:home",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def channel_detail_keyboard(
    channel_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧪 Test pubblicazione",
                    callback_data=(
                        f"channel:test:{channel_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Rimuovi canale",
                    callback_data=(
                        f"channel:remove:{channel_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Canali",
                    callback_data="menu:channels",
                )
            ],
        ]
    )


async def show_channels(
    query: CallbackQuery,
) -> None:
    settings = get_settings()

    channels = await list_channels(
        settings.admin_user_id
    )

    if channels:
        text = (
            "📢 <b>I tuoi canali</b>\n\n"
            "Seleziona un canale oppure "
            "aggiungine uno nuovo."
        )
    else:
        text = (
            "📢 <b>I tuoi canali</b>\n\n"
            "Non hai ancora collegato "
            "nessun canale."
        )

    if query.message is not None:
        await query.message.edit_text(
            text,
            reply_markup=channels_keyboard(channels),
        )

    await query.answer()


@router.callback_query(
    F.data == "menu:channels"
)
async def channels_menu(
    query: CallbackQuery,
) -> None:
    await show_channels(query)


@router.callback_query(
    F.data == "channels:add"
)
async def add_channel_start(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    if (
        query.from_user.id
        != settings.admin_user_id
    ):
        await query.answer(
            "Non autorizzato.",
            show_alert=True,
        )
        return

    await state.set_state(
        AddChannelStates.waiting_forward
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Annulla",
                    callback_data="channels:cancel_add",
                )
            ]
        ]
    )

    if query.message is not None:
        await query.message.edit_text(
            "➕ <b>Aggiungi canale</b>\n\n"
            "1️⃣ Aggiungi questo bot come "
            "<b>amministratore</b> del canale.\n\n"
            "2️⃣ Assicurati che possa "
            "<b>pubblicare messaggi</b>.\n\n"
            "3️⃣ Inoltrami qui un qualsiasi "
            "messaggio pubblicato nel canale.\n\n"
            "Il bot riconoscerà automaticamente "
            "il canale.",
            reply_markup=keyboard,
        )

    await query.answer()


@router.callback_query(
    F.data == "channels:cancel_add"
)
async def cancel_add_channel(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await show_channels(query)


@router.message(
    AddChannelStates.waiting_forward
)
async def receive_forwarded_channel_message(
    message: Message,
    bot: Bot,
    state: FSMContext,
) -> None:
    settings = get_settings()

    if message.from_user is None:
        return

    if (
        message.from_user.id
        != settings.admin_user_id
    ):
        return

    origin = message.forward_origin

    if not isinstance(
        origin,
        MessageOriginChannel,
    ):
        await message.answer(
            "❌ Questo messaggio non sembra "
            "provenire da un canale.\n\n"
            "Inoltra direttamente un messaggio "
            "pubblicato nel canale."
        )
        return

    channel_chat = origin.chat

    bot_user = await bot.get_me()

    try:
        member = await bot.get_chat_member(
            chat_id=channel_chat.id,
            user_id=bot_user.id,
        )
    except TelegramAPIError:
        await message.answer(
            "❌ Non riesco ad accedere al canale.\n\n"
            "Controlla di aver aggiunto il bot "
            "come amministratore."
        )
        return

    if not isinstance(
        member,
        ChatMemberAdministrator,
    ):
        await message.answer(
            "❌ Il bot è stato trovato, "
            "ma non è amministratore del canale."
        )
        return

    if member.can_post_messages is not True:
        await message.answer(
            "❌ Il bot è amministratore, "
            "ma non può pubblicare messaggi.\n\n"
            "Abilita il permesso per "
            "pubblicare messaggi e riprova."
        )
        return

    channel = await save_channel(
        owner_telegram_user_id=(
            message.from_user.id
        ),
        telegram_chat_id=channel_chat.id,
        title=(
            channel_chat.title
            or "Canale senza nome"
        ),
        username=channel_chat.username,
        can_post_messages=True,
    )

    await state.clear()

    username_text = (
        f"@{escape(channel.username)}"
        if channel.username
        else "Privato / senza username"
    )

    await message.answer(
        "✅ <b>Canale collegato!</b>\n\n"
        f"📢 Nome: "
        f"<b>{escape(channel.title)}</b>\n"
        f"🔗 Username: {username_text}\n"
        f"🆔 Chat ID: "
        f"<code>{channel.telegram_chat_id}</code>\n"
        "✅ Permesso pubblicazione: OK",
        reply_markup=channel_detail_keyboard(
            channel.id
        ),
    )


@router.callback_query(
    F.data.startswith("channel:view:")
)
async def channel_detail(
    query: CallbackQuery,
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

    username_text = (
        f"@{escape(channel.username)}"
        if channel.username
        else "Privato / senza username"
    )

    if query.message is not None:
        await query.message.edit_text(
            "📢 <b>Dettagli canale</b>\n\n"
            f"Nome: "
            f"<b>{escape(channel.title)}</b>\n"
            f"Username: {username_text}\n"
            f"Chat ID: "
            f"<code>{channel.telegram_chat_id}</code>\n"
            "Permesso pubblicazione: ✅",
            reply_markup=channel_detail_keyboard(
                channel.id
            ),
        )

    await query.answer()


@router.callback_query(
    F.data.startswith("channel:test:")
)
async def test_channel(
    query: CallbackQuery,
    bot: Bot,
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

    try:
        await bot.send_message(
            chat_id=channel.telegram_chat_id,
            text=(
                "🧪 <b>Test AmazonDealsBot</b>\n\n"
                "✅ Il canale è collegato "
                "correttamente.\n"
                "🚧 Sistema offerte in sviluppo."
            ),
        )
    except TelegramAPIError:
        await query.answer(
            "❌ Pubblicazione fallita. "
            "Controlla i permessi del bot.",
            show_alert=True,
        )
        return

    await query.answer(
        "✅ Messaggio pubblicato nel canale!",
        show_alert=True,
    )


@router.callback_query(
    F.data.startswith("channel:remove:")
)
async def remove_channel(
    query: CallbackQuery,
) -> None:
    settings = get_settings()

    if query.data is None:
        return

    channel_id = int(
        query.data.split(":")[-1]
    )

    removed = await disable_channel(
        channel_id,
        settings.admin_user_id,
    )

    if not removed:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )
        return

    await query.answer(
        "Canale rimosso.",
    )

    await show_channels(query)
