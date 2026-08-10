from datetime import timezone
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import get_settings
from app.history_store import list_history


router = Router(name="history")


@router.callback_query(F.data == "stats:history")
async def history_open(query: CallbackQuery) -> None:
    settings = get_settings()
    items = await list_history(settings.admin_user_id, 30)
    lines = ["📜 <b>Storico</b>", ""]
    if not items:
        lines.append("Nessun evento disponibile.")
    for item in items:
        dt = item.at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        icon = {"published": "✅", "rejected": "❌", "failed": "⚠️"}.get(item.kind, "•")
        lines.append(
            f"{icon} {dt.strftime('%d/%m %H:%M')} • {escape(item.channel_title)}\n"
            f"   {escape(item.title[:55])} • <code>{escape(item.asin)}</code>"
        )
    if query.message:
        await query.message.edit_text(
            "\n".join(lines)[:3900],
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Aggiorna", callback_data="stats:history")],
                [InlineKeyboardButton(text="⬅️ Statistiche", callback_data="menu:stats")],
            ]),
        )
    await query.answer()
