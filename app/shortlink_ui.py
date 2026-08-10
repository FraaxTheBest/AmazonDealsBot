from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import get_settings
from app.shortlink_store import get_shortlink_stats


router = Router(name="shortlink_ui")


@router.callback_query(F.data == "settings:shortlink")
async def shortlink_open(query: CallbackQuery) -> None:
    settings = get_settings()
    stats = await get_shortlink_stats(settings.admin_user_id)
    enabled = bool(settings.shortlink_enabled and settings.shortlink_base_url)
    base = settings.shortlink_base_url or "non configurata"
    if query.message is not None:
        await query.message.edit_text(
            "🔗 <b>Shortlink proprietario</b>\n\n"
            f"Stato: <b>{'ON' if enabled else 'OFF'}</b>\n"
            f"Base URL: <code>{escape(base)}</code>\n"
            f"Link creati: <b>{stats.links}</b>\n"
            f"Click registrati: <b>{stats.clicks}</b>\n\n"
            "Quando è attivo, i post automatici/programmatici possono usare "
            "il redirect /r/&lt;codice&gt; della web app. Il link finale continua "
            "a puntare ad Amazon con il Tracking ID previsto.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Aggiorna", callback_data="settings:shortlink")],
                    [InlineKeyboardButton(text="⬅️ Impostazioni", callback_data="menu:settings")],
                ]
            ),
        )
    await query.answer()
