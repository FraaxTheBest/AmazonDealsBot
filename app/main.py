import asyncio
import logging
import sys
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.channels import router as channels_router
from app.posts import router as posts_router
from app.config import get_settings
from app.database import init_db, register_user


router = Router(name="main")


def main_menu_keyboard() -> InlineKeyboardMarkup:
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


def main_menu_text(
    first_name: str | None,
) -> str:
    name = escape(
        first_name or "Admin"
    )

    return (
        "🛒 <b>AmazonDealsBot</b>\n\n"
        f"👋 Ciao <b>{name}</b>!\n"
        "🔐 Ruolo: 👑 Amministratore\n\n"
        "Seleziona una funzione:"
    )


@router.message(CommandStart())
async def start_handler(
    message: Message,
) -> None:
    if message.from_user is None:
        return

    settings = get_settings()

    is_admin = (
        message.from_user.id
        == settings.admin_user_id
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
        main_menu_text(
            message.from_user.first_name
        ),
        reply_markup=main_menu_keyboard(),
    )


async def back_home(
    query: CallbackQuery,
) -> None:
    if query.message is not None:
        await query.message.edit_text(
            main_menu_text(
                query.from_user.first_name
            ),
            reply_markup=main_menu_keyboard(),
        )

    await query.answer()


@router.callback_query(
    F.data == "menu:create_post"
)
@router.callback_query(
    F.data == "menu:autopost"
)
@router.callback_query(
    F.data == "menu:templates"
)
@router.callback_query(
    F.data == "menu:stats"
)
@router.callback_query(
    F.data == "menu:settings"
)
async def future_sections(
    query: CallbackQuery,
) -> None:
    names = {
        "menu:autopost": "🤖 Autoposting",
        "menu:templates": "📝 Template",
        "menu:stats": "📊 Statistiche",
        "menu:settings": "⚙️ Impostazioni",
    }

    section = names.get(
        query.data,
        "Funzione",
    )

    await query.answer(
        f"{section} — arriverà "
        "nelle prossime fasi.",
        show_alert=True,
    )


async def main() -> None:
    settings = get_settings()

    await init_db()

    logging.info(
        "Database inizializzato."
    )

    bot = Bot(
        token=(
            settings.bot_token
            .get_secret_value()
        ),
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()

    dispatcher.include_router(
        channels_router
    )

    dispatcher.include_router(
        posts_router
    )
    
    dispatcher.include_router(
        router
    )

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    logging.info(
        "AmazonDealsBot avviato."
    )

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
