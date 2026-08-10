from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import get_settings
from app.shortlink_store import get_shortlink_stats
from app.system_health import collect_health


router = Router(name="admin_settings")


def _yes(value: bool) -> str:
    return "✅" if value else "❌"


def _keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🩺 Health", callback_data="settings:health"),
                InlineKeyboardButton(text="📦 Amazon", callback_data="settings:provider"),
            ],
            [
                InlineKeyboardButton(text="🏷 Affiliazione", callback_data="settings:affiliate"),
                InlineKeyboardButton(text="🧠 AI", callback_data="settings:ai"),
            ],
            [
                InlineKeyboardButton(text="🔗 Shortlink", callback_data="settings:shortlink"),
                InlineKeyboardButton(text="🧰 Extra", callback_data="settings:extras"),
            ],
            [InlineKeyboardButton(text="🏠 Home", callback_data="menu:home")],
        ]
    )


async def _text() -> str:
    settings = get_settings()
    health = await collect_health()
    short = await get_shortlink_stats(settings.admin_user_id)
    return (
        "⚙️ <b>Impostazioni</b>\n\n"
        f"Ambiente: <b>{escape(settings.app_env)}</b>\n"
        f"Database: <b>{escape(health.db_backend)}</b> {_yes(health.db_ok)}\n"
        f"Scheduler: {_yes(health.manual_scheduler_ok)}\n"
        f"Autopost scheduler: {_yes(health.autopost_scheduler_ok)}\n\n"
        f"Amazon provider: <b>{escape(health.amazon_provider)}</b> "
        f"{_yes(health.amazon_configured)}\n"
        f"AI configurata: {_yes(health.ai_configured)}\n"
        f"Shortlink: {_yes(health.shortlink_configured)} "
        f"({short.links} link / {short.clicks} click)\n"
        f"Web dashboard: {_yes(health.web_configured)}\n\n"
        "I segreti restano nel file .env e non vengono mostrati qui."
    )


@router.callback_query(F.data == "menu:settings")
async def settings_open(query: CallbackQuery) -> None:
    if query.message is not None:
        await query.message.edit_text(await _text(), reply_markup=_keyboard())
    await query.answer()


@router.callback_query(F.data == "settings:health")
async def settings_health(query: CallbackQuery) -> None:
    health = await collect_health()
    text = (
        "🩺 <b>Health check</b>\n\n"
        f"Database: {_yes(health.db_ok)}\n"
        f"Scheduler programmati: {_yes(health.manual_scheduler_ok)}\n"
        f"Scheduler autopost: {_yes(health.autopost_scheduler_ok)}\n"
        f"Provider Amazon: {_yes(health.amazon_configured)}\n"
        f"AI: {_yes(health.ai_configured)}\n"
        f"Shortlink: {_yes(health.shortlink_configured)}\n"
        f"Dashboard web: {_yes(health.web_configured)}"
    )
    if query.message is not None:
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Ricontrolla", callback_data="settings:health")],
                    [InlineKeyboardButton(text="⬅️ Impostazioni", callback_data="menu:settings")],
                ]
            ),
        )
    await query.answer()
