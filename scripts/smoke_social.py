"""Smoke test locale Social Hub Phase 1.

Non effettua chiamate reali a Meta e non stampa segreti.
"""

import asyncio
import os
import tempfile
import sys
from pathlib import Path


# Permette di eseguire questo file direttamente con:
# python scripts\\smoke_social.py
# aggiungendo la root del progetto al Python path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Valori finti PRIMA di importare app.config/app.database.
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN_NOT_REAL")
os.environ.setdefault("ADMIN_USER_ID", "123456789")
os.environ["SOCIAL_ENABLED"] = "true"
os.environ["SOCIAL_FACEBOOK_ENABLED"] = "true"
os.environ["SOCIAL_INSTAGRAM_ENABLED"] = "true"
os.environ["META_SYSTEM_USER_ACCESS_TOKEN"] = "TEST_META_TOKEN_NOT_REAL"
os.environ["FACEBOOK_PAGE_ID"] = "1234567890"
os.environ["INSTAGRAM_ACCESS_TOKEN"] = "TEST_IG_TOKEN_NOT_REAL"
os.environ["INSTAGRAM_ACCOUNT_ID"] = "9876543210"

_tmp = tempfile.NamedTemporaryFile(prefix="social_smoke_", suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(_tmp.name).as_posix()}"

from sqlalchemy import inspect  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.model_registry import import_all_models  # noqa: E402
from app.social.base import SocialPost  # noqa: E402
from app.social_service import SocialService  # noqa: E402
from app.social_store import create_social_draft, get_social_draft  # noqa: E402


async def main() -> None:
    import_all_models()
    await init_db()

    settings = get_settings()
    service = SocialService(settings)

    assert service.platform_status("facebook")[0] is True
    assert service.platform_status("instagram")[0] is True
    assert service.platform_status("pinterest")[0] is False
    assert service.platform_status("telegram")[0] is False
    assert service.platform_status("whatsapp")[0] is False

    post = SocialPost(
        title="Smoke Social Hub",
        description="Test locale",
        link="https://example.com",
        image_url="https://example.com/image.jpg",
        hashtags="#test",
    )
    draft = await create_social_draft(
        settings.admin_user_id,
        post,
        ["facebook", "instagram"],
    )
    saved = await get_social_draft(settings.admin_user_id, draft.id)
    assert saved is not None
    assert saved.title == "Smoke Social Hub"
    assert saved.destinations() == ["facebook", "instagram"]

    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    assert "social_drafts" in tables

    print("SMOKE SOCIAL OK")
    print("Social Hub: ON")
    print("Facebook: READY (credenziali test, nessuna chiamata API)")
    print("Instagram: READY (credenziali test, nessuna chiamata API)")
    print("Pinterest: LOCKED")
    print("Telegram: LOCKED")
    print("WhatsApp: LOCKED")
    print("Tabella social_drafts: OK")
    print("Nessun segreto stampato.")

    await engine.dispose()
    try:
        Path(_tmp.name).unlink(missing_ok=True)
    except OSError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
