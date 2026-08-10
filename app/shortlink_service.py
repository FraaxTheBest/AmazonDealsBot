from urllib.parse import urljoin

from app.amazon.models import ProductSnapshot
from app.config import get_settings
from app.shortlink_store import create_or_get_shortlink
from app.template_engine import get_public_url


async def build_offer_url(
    *,
    owner_telegram_user_id: int,
    channel_id: int,
    product: ProductSnapshot,
) -> str:
    destination = get_public_url(product)
    settings = get_settings()

    if not settings.shortlink_enabled or not settings.shortlink_base_url:
        return destination

    link = await create_or_get_shortlink(
        owner_telegram_user_id=owner_telegram_user_id,
        channel_id=channel_id,
        destination_url=destination,
        asin=product.asin,
    )
    base = settings.shortlink_base_url.rstrip("/") + "/"
    return urljoin(base, f"r/{link.code}")
