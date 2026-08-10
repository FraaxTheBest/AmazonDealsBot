import logging
import time

from aiogram import Bot

from app.config import get_settings


_last_sent: dict[str, float] = {}


async def notify_admin_error(
    bot: Bot | None,
    key: str,
    message: str,
    throttle_seconds: int = 900,
) -> None:
    settings = get_settings()
    if not settings.admin_notifications_enabled or bot is None:
        return
    now = time.monotonic()
    if now - _last_sent.get(key, 0.0) < throttle_seconds:
        return
    _last_sent[key] = now
    try:
        await bot.send_message(
            settings.admin_user_id,
            "🚨 <b>AmazonDealsBot</b>\n\n" + message[:3000],
        )
    except Exception:
        logging.exception("Impossibile inviare notifica admin per %s.", key)
