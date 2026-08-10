import asyncio
import logging
import sys
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.admin_ui import router as admin_router
from app.affiliate_ui import router as affiliate_router
from app.ai_ui import router as ai_router
from app.autopost_advanced_ui import router as autopost_advanced_router
from app.autopost_queue_ui import router as autopost_queue_router
from app.autopost_runtime_ui import router as autopost_runtime_router
from app.autopost_scheduler import start_autopost_scheduler, stop_autopost_scheduler
from app.autoposting import router as autoposting_router
from app.channels import router as channels_router
from app.config import get_settings
from app.database import init_db, register_user
from app.dedupe_ui import router as dedupe_router
from app.extras_ui import router as extras_router
from app.history_ui import router as history_router
from app.model_registry import import_all_models
from app.pipeline_ui import router as pipeline_router
from app.post_draft_bridge import router as draft_bridge_router
from app.posts import router as posts_router
from app.provider_ui import router as provider_router
from app.scheduling import router as scheduling_router
from app.scheduler_service import start_scheduler, stop_scheduler
from app.shortlink_ui import router as shortlink_router
from app.security import AdminOnlyMiddleware, SimpleRateLimitMiddleware
from app.stats_ui import router as stats_router
from app.templates import router as templates_router


router = Router(name="main")


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Canali", callback_data="menu:channels"),
            InlineKeyboardButton(text="➕ Crea Post", callback_data="menu:create_post"),
        ],
        [
            InlineKeyboardButton(text="🗓 Programmati", callback_data="menu:scheduled"),
            InlineKeyboardButton(text="📝 Template", callback_data="menu:templates"),
        ],
        [
            InlineKeyboardButton(text="🤖 Autoposting", callback_data="menu:autopost"),
            InlineKeyboardButton(text="📊 Statistiche", callback_data="menu:stats"),
        ],
        [InlineKeyboardButton(text="⚙️ Impostazioni", callback_data="menu:settings")],
    ])


def main_menu_text(first_name: str | None) -> str:
    name = escape(first_name or "Admin")
    return (
        "🛒 <b>AmazonDealsBot</b>\n\n"
        f"👋 Ciao <b>{name}</b>!\n"
        "🔐 Ruolo: 👑 Amministratore\n\n"
        "Seleziona una funzione:"
    )


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return
    settings = get_settings()
    if message.from_user.id != settings.admin_user_id:
        await message.answer("⛔ <b>Accesso non autorizzato.</b>")
        return
    await register_user(
        telegram_user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        is_admin=True,
    )
    await message.answer(
        main_menu_text(message.from_user.first_name),
        reply_markup=main_menu_keyboard(),
    )


@router.callback_query(F.data == "menu:home")
async def back_home(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if query.message is not None:
        try:
            await query.message.edit_text(
                main_menu_text(query.from_user.first_name),
                reply_markup=main_menu_keyboard(),
            )
        except Exception:
            await query.message.answer(
                main_menu_text(query.from_user.first_name),
                reply_markup=main_menu_keyboard(),
            )
    await query.answer()


async def main() -> None:
    settings = get_settings()
    import_all_models()
    await init_db()
    logging.info("Database inizializzato.")

    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(AdminOnlyMiddleware(settings.admin_user_id))
    dispatcher.update.outer_middleware(SimpleRateLimitMiddleware())

    dispatcher.include_router(router)
    dispatcher.include_router(channels_router)
    dispatcher.include_router(posts_router)
    dispatcher.include_router(draft_bridge_router)
    dispatcher.include_router(scheduling_router)
    dispatcher.include_router(autoposting_router)
    dispatcher.include_router(autopost_runtime_router)
    dispatcher.include_router(autopost_queue_router)
    dispatcher.include_router(autopost_advanced_router)
    dispatcher.include_router(dedupe_router)
    dispatcher.include_router(pipeline_router)
    dispatcher.include_router(templates_router)
    dispatcher.include_router(stats_router)
    dispatcher.include_router(history_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(provider_router)
    dispatcher.include_router(affiliate_router)
    dispatcher.include_router(ai_router)
    dispatcher.include_router(shortlink_router)
    dispatcher.include_router(extras_router)

    await bot.delete_webhook(drop_pending_updates=True)

    manual_scheduler_started = False
    autopost_scheduler_started = False
    try:
        await start_scheduler(bot)
        manual_scheduler_started = True
        await start_autopost_scheduler(bot)
        autopost_scheduler_started = True
        logging.info("AmazonDealsBot final phases avviato.")
        await dispatcher.start_polling(bot)
    finally:
        if autopost_scheduler_started:
            stop_autopost_scheduler()
        if manual_scheduler_started:
            stop_scheduler()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    asyncio.run(main())
