from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.amazon.creators_api import CreatorsAPIClient
from app.config import get_settings


router = Router(name="provider_ui")


def _keyboard(can_test: bool) -> InlineKeyboardMarkup:
    rows = []
    if can_test:
        rows.append(
            [InlineKeyboardButton(text="🧪 Test connessione", callback_data="provider:test")]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Impostazioni", callback_data="menu:settings")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "settings:provider")
async def provider_open(query: CallbackQuery) -> None:
    settings = get_settings()
    is_creators = settings.amazon_provider == "creators"
    configured = CreatorsAPIClient().configured() if is_creators else True
    if query.message is not None:
        await query.message.edit_text(
            "📦 <b>Amazon Provider</b>\n\n"
            f"Provider: <b>{escape(settings.amazon_provider)}</b>\n"
            f"Marketplace: <code>{escape(settings.amazon_marketplace)}</code>\n"
            f"Creators API configurata: <b>{'SÌ' if configured else 'NO'}</b>\n\n"
            "Per attivare il provider reale imposta AMAZON_PROVIDER=creators "
            "e le credenziali Creators API nel file .env locale.\n"
            "Il bot non mostra mai Client Secret o token.",
            reply_markup=_keyboard(is_creators and configured),
        )
    await query.answer()


@router.callback_query(F.data == "provider:test")
async def provider_test(query: CallbackQuery) -> None:
    client = CreatorsAPIClient()
    if not client.configured():
        await query.answer("Creators API non configurata.", show_alert=True)
        return
    try:
        await client.test_connection()
    except Exception as exc:
        await query.answer(f"Test fallito: {str(exc)[:160]}", show_alert=True)
        return
    await query.answer("✅ Autenticazione Creators API riuscita.", show_alert=True)
