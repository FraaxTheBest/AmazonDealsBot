from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.ai_service import ai_available, enhance_product_with_ai
from app.ai_store import get_or_create_ai_config, set_ai_enabled
from app.amazon.models import ProductSnapshot
from app.config import get_settings


router = Router(name="ai_ui")


def _keyboard(enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("🔴 Disattiva AI" if enabled else "🟢 Attiva AI"),
                    callback_data="ai:toggle",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧪 Test AI",
                    callback_data="ai:test",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Impostazioni",
                    callback_data="menu:settings",
                )
            ],
        ]
    )


async def _show(query: CallbackQuery) -> None:
    settings = get_settings()
    config = await get_or_create_ai_config(settings.admin_user_id)
    key_state = "✅ configurata" if ai_available() else "❌ non configurata"
    if query.message is not None:
        await query.message.edit_text(
            "🧠 <b>AI opzionale</b>\n\n"
            f"Stato: <b>{'ON' if config.enabled else 'OFF'}</b>\n"
            f"API key: <b>{key_state}</b>\n"
            f"Modello: <code>{escape(config.model)}</code>\n\n"
            "L'AI può generare {aiTitle}, {aiDescription} e {aiEmoji}.\n"
            "Prezzi, sconti e dati Amazon non vengono inventati.\n\n"
            "Se manca la chiave, il bot continua a funzionare senza AI.",
            reply_markup=_keyboard(config.enabled),
        )
    await query.answer()


@router.callback_query(F.data == "settings:ai")
async def ai_open(query: CallbackQuery) -> None:
    await _show(query)


@router.callback_query(F.data == "ai:toggle")
async def ai_toggle(query: CallbackQuery) -> None:
    settings = get_settings()
    config = await get_or_create_ai_config(settings.admin_user_id)
    if not config.enabled and not ai_available():
        await query.answer(
            "Imposta OPENAI_API_KEY nel file .env locale prima di attivare l'AI.",
            show_alert=True,
        )
        return
    await set_ai_enabled(settings.admin_user_id, not config.enabled)
    await _show(query)


@router.callback_query(F.data == "ai:test")
async def ai_test(query: CallbackQuery) -> None:
    settings = get_settings()
    product = ProductSnapshot(
        asin="B0AITEST01",
        title=(
            "Supporto Monitor da Scrivania Regolabile con Braccio Ergonomico "
            "per Schermi da 19 a 32 Pollici"
        ),
        detail_url="https://www.amazon.it/dp/B0AITEST01",
        brand="Demo",
        description="Supporto regolabile per monitor. Dati esclusivamente demo.",
    )
    result = await enhance_product_with_ai(settings.admin_user_id, product)
    if not result.used_ai:
        await query.answer(
            f"Test non eseguito: {result.error_message or 'AI disattivata.'}",
            show_alert=True,
        )
        return
    await query.answer("Test AI riuscito.")
    if query.message is not None:
        await query.message.answer(
            "🧪 <b>Risultato test AI</b>\n\n"
            f"{escape(result.product.ai_emoji or '')} "
            f"<b>{escape(result.product.ai_title or '')}</b>\n"
            f"{escape(result.product.ai_description or '')}"
        )
