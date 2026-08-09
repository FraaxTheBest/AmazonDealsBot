import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.config import get_settings


router = Router(name="main")


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    """Gestisce il comando /start."""

    if message.from_user is None:
        return

    settings = get_settings()

    if message.from_user.id == settings.admin_user_id:
        role = "👑 Amministratore"
    else:
        role = "👤 Utente"

    await message.answer(
        "🛒 <b>AmazonDealsBot</b>\n\n"
        "✅ Bot avviato correttamente.\n"
        f"🆔 Il tuo ID: <code>{message.from_user.id}</code>\n"
        f"🔐 Ruolo: {role}\n\n"
        "🚧 Il progetto è attualmente in fase di sviluppo."
    )


async def main() -> None:
    settings = get_settings()

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)

    logging.info("AmazonDealsBot avviato.")

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    asyncio.run(main())
