import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import inspect

from app.amazon.provider_factory import DemoProvider
from app.config import get_settings
from app.database import Base, engine, init_db
from app.model_registry import import_all_models
from app.template_engine import render_post


async def main() -> None:
    settings = get_settings()
    import_all_models()
    await init_db()

    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda conn: inspect(conn).get_table_names())

    demo = DemoProvider._products(settings.amazon_partner_tag)[0]
    rendered = render_post(demo)
    assert demo.offer_type == "lightning"
    assert rendered
    required = {
        "publication_events",
        "autopost_candidates",
        "channel_autopost_advanced_configs",
        "autopost_scan_metrics",
        "channel_affiliate_configs",
        "short_links",
        "ai_configs",
        "post_drafts",
    }
    missing = sorted(required.difference(tables))
    if missing:
        raise RuntimeError("Tabelle mancanti: " + ", ".join(missing))

    print("SMOKE FINAL OK")
    print(f"Database backend configurato: {settings.database_url.split(':', 1)[0]}")
    print(f"Tabelle rilevate: {len(tables)}")
    print(f"Provider: {settings.amazon_provider}")
    print("DEMO offer type: lightning OK")
    print("Template engine: OK")
    print("Nessun segreto stampato.")


if __name__ == "__main__":
    asyncio.run(main())
