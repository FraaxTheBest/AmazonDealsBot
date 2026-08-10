from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.affiliate_store import (
    get_channel_partner_tag,
    get_effective_partner_tag,
    reset_channel_partner_tag,
    set_channel_partner_tag,
)
from app.config import get_settings
from app.database import get_channel, list_channels


router = Router(name="affiliate_ui")


class AffiliateStates(StatesGroup):
    waiting_tag = State()


def _channels_keyboard(channels) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"📢 {channel.title[:32]}",
                callback_data=f"affiliate:channel:{channel.id}",
            )
        ]
        for channel in channels
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Impostazioni", callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _channel_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Cambia tag", callback_data=f"affiliate:set:{channel_id}")],
            [InlineKeyboardButton(text="↩️ Usa tag globale", callback_data=f"affiliate:reset:{channel_id}")],
            [InlineKeyboardButton(text="⬅️ Canali", callback_data="settings:affiliate")],
        ]
    )


@router.callback_query(F.data == "settings:affiliate")
async def affiliate_open(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    await state.set_state(None)
    channels = await list_channels(settings.admin_user_id)
    if query.message is not None:
        await query.message.edit_text(
            "🏷 <b>Affiliazione Amazon</b>\n\n"
            "Puoi usare il Tracking ID globale del file .env oppure "
            "impostarne uno diverso per ogni canale.",
            reply_markup=_channels_keyboard(channels),
        )
    await query.answer()


@router.callback_query(F.data.startswith("affiliate:channel:"))
async def affiliate_channel(query: CallbackQuery) -> None:
    if not query.data:
        return
    settings = get_settings()
    channel_id = int(query.data.rsplit(":", 1)[-1])
    channel = await get_channel(channel_id, settings.admin_user_id)
    if channel is None:
        await query.answer("Canale non trovato.", show_alert=True)
        return
    custom = await get_channel_partner_tag(settings.admin_user_id, channel_id)
    effective = await get_effective_partner_tag(settings.admin_user_id, channel_id)
    if query.message is not None:
        await query.message.edit_text(
            "🏷 <b>Tracking ID canale</b>\n\n"
            f"📢 {escape(channel.title)}\n"
            f"Tag effettivo: <code>{escape(effective)}</code>\n"
            f"Origine: <b>{'personalizzato' if custom else 'globale'}</b>",
            reply_markup=_channel_keyboard(channel_id),
        )
    await query.answer()


@router.callback_query(F.data.startswith("affiliate:set:"))
async def affiliate_set_start(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data:
        return
    channel_id = int(query.data.rsplit(":", 1)[-1])
    await state.update_data(affiliate_channel_id=channel_id)
    await state.set_state(AffiliateStates.waiting_tag)
    if query.message is not None:
        await query.message.edit_text(
            "🏷 <b>Nuovo Tracking ID</b>\n\n"
            "Invia il Tracking ID, ad esempio <code>mio-tag-21</code>.\n"
            "Non inviare password o credenziali API."
        )
    await query.answer()


@router.message(AffiliateStates.waiting_tag)
async def affiliate_set_value(message: Message, state: FSMContext) -> None:
    if not message.text:
        await message.answer("Invia un Tracking ID testuale.")
        return
    data = await state.get_data()
    channel_id = data.get("affiliate_channel_id")
    if channel_id is None:
        await state.clear()
        return
    settings = get_settings()
    try:
        config = await set_channel_partner_tag(
            settings.admin_user_id,
            int(channel_id),
            message.text,
        )
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    await state.clear()
    await message.answer(
        "✅ Tracking ID salvato: "
        f"<code>{escape(config.partner_tag)}</code>"
    )


@router.callback_query(F.data.startswith("affiliate:reset:"))
async def affiliate_reset(query: CallbackQuery) -> None:
    if not query.data:
        return
    settings = get_settings()
    channel_id = int(query.data.rsplit(":", 1)[-1])
    await reset_channel_partner_tag(settings.admin_user_id, channel_id)
    await query.answer("Ripristinato il tag globale.", show_alert=True)
