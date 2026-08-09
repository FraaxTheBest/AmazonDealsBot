from decimal import Decimal
from typing import Protocol

from app.amazon.models import ProductSnapshot
from app.config import get_settings


class AmazonProvider(Protocol):
    async def get_product(
        self,
        asin: str,
    ) -> ProductSnapshot:
        ...


class MockAmazonProvider:
    async def get_product(
        self,
        asin: str,
    ) -> ProductSnapshot:
        settings = get_settings()

        affiliate_url = (
            f"https://www.amazon.it/dp/{asin}"
            f"?tag={settings.amazon_partner_tag}"
        )

        return ProductSnapshot(
            asin=asin,
            title=f"Prodotto Amazon di test ({asin})",
            brand="AmazonDealsBot Demo",
            detail_url=f"https://www.amazon.it/dp/{asin}",
            affiliate_url=affiliate_url,
            affiliate_short_url=None,
            image_url=None,
            current_price=Decimal("79.99"),
            original_price=Decimal("99.99"),
            discount_percentage=Decimal("20"),
            rating=Decimal("4.7"),
            reviews_count=66,
            availability="Disponibile",
            seller="AmazonDealsBot Demo",
            ships_from="Amazon",
        )
