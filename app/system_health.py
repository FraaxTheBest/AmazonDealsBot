from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import text

from app.config import get_settings
from app.database import SessionLocal


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    db_ok: bool
    db_backend: str
    manual_scheduler_ok: bool
    autopost_scheduler_ok: bool
    amazon_provider: str
    amazon_configured: bool
    ai_configured: bool
    shortlink_configured: bool
    web_configured: bool


def database_backend() -> str:
    url = get_settings().database_url
    scheme = urlsplit(url.replace("+aiosqlite", "").replace("+asyncpg", "")).scheme
    return scheme or "unknown"


async def database_ok() -> bool:
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def collect_health() -> HealthSnapshot:
    settings = get_settings()

    try:
        from app.scheduler_service import scheduler_running
        manual_scheduler_ok = bool(scheduler_running())
    except Exception:
        manual_scheduler_ok = False

    try:
        from app.autopost_scheduler import autopost_scheduler_running
        autopost_scheduler_ok = bool(autopost_scheduler_running())
    except Exception:
        autopost_scheduler_ok = False

    creators_configured = bool(
        settings.amazon_creators_client_id
        and settings.amazon_creators_client_secret
    )
    amazon_configured = (
        True if settings.amazon_provider == "demo" else creators_configured
    )

    return HealthSnapshot(
        db_ok=await database_ok(),
        db_backend=database_backend(),
        manual_scheduler_ok=manual_scheduler_ok,
        autopost_scheduler_ok=autopost_scheduler_ok,
        amazon_provider=settings.amazon_provider,
        amazon_configured=amazon_configured,
        ai_configured=bool(settings.openai_api_key),
        shortlink_configured=bool(
            settings.shortlink_enabled and settings.shortlink_base_url
        ),
        web_configured=bool(settings.web_enabled and settings.web_admin_token),
    )
