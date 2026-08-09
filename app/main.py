import asyncio
import logging
import sys

from aiogram import Bot, CallbackQuery, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.config import get_settings
from app.database import init_db, register_user


router = Router(name="main")


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Menu principale dell'amministratore."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Canali",
                    callback_data="menu:channels",
                ),
                InlineKeyboardButton(
                    text="➕ Crea Post",
                    callback_data="menu:create_post",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Autoposting",
                    callback_data="menu:autopost",
                ),
                InlineKeyboardButton(
                    text="📝 Template",
                    callback_data="menu:templates",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Statistiche",
                    callback_data="menu:stats",
                ),
                InlineKeyboardButton(
                    text="⚙️ Impostazioni",
                    callback_data="menu:settings",
                ),
            ],
        ]
    )


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Registra l'utente e mostra il menu principale."""

    if message.from_user is None:
        return

    settings = get_settings()

    is_admin = (
        message.from_user.id == settings.admin_user_id
    )

    if not is_admin:
        await message.answer(
            "⛔ <b>Accesso non autorizzato.</b>"
        )
        return

    await register_user(
        telegram_user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=True,
    )

    await message.answer(
        "🛒 <b>AmazonDealsBot</b>\n\n"
        f"👋 Ciao <b>{message.from_user.first_name}</b>!\n"
        "🔐 Ruolo: 👑 Amministratore\n\n"
        "Seleziona una funzione:",
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data.startswith("menu:"))
async def menu_callback(query: CallbackQuery) -> None:
    """Gestisce temporaneamente i pulsanti del menu."""

    if query.data is None:
        await query.answer()
        return

    sections = {
        "menu:channels": "📢 Gestione canali",
        "menu:create_post": "➕ Crea Post",
        "menu:autopost": "🤖 Autoposting",
        "menu:templates": "📝 Template",
        "menu:stats": "📊 Statistiche",
        "menu:settings": "⚙️ Impostazioni",
    }

    section = sections.get(
        query.data,
        "Funzione sconosciuta",
    )

    await query.answer(
        f"{section} — arriverà nelle prossime fasi.",
        show_alert=True,
    )


async def main() -> None:
    settings = get_settings()

    await init_db()

    logging.info("Database inizializzato.")

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    logging.info("AmazonDealsBot avviato.")

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format=(
            "%(asctime)s | %(levelname)s | "
            "%(name)s | %(message)s"
        ),
    )

    asyncio.run(main())
