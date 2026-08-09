from decimal import Decimal
from typing import Protocol

from app.amazon.models import ProductSnapshot
from app.config import get_settings


DEMO_PRIMARY_IMAGE = (
    "https://placehold.co/"
    "1200x1200/png"
    "?text=PRIMARY+IMAGE+DEMO"
)

DEMO_VARIANT_IMAGES = [
    (
        "https://placehold.co/"
        "1200x1200/png"
        "?text=VARIANTE+2+DEMO"
    ),
    (
        "https://placehold.co/"
        "1200x1200/png"
        "?text=VARIANTE+3+DEMO"
    ),
    (
        "https://placehold.co/"
        "1200x1200/png"
        "?text=VARIANTE+4+DEMO"
    ),
]


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
            title=(
                "Prodotto Amazon di test "
                f"({asin})"
            ),
            brand="AmazonDealsBot Demo",

            detail_url=(
                f"https://www.amazon.it/"
                f"dp/{asin}"
            ),

            affiliate_url=affiliate_url,

            affiliate_short_url=None,

            # La PRIMARY viene scelta
            # automaticamente.
            image_url=DEMO_PRIMARY_IMAGE,

            primary_image_url=(
                DEMO_PRIMARY_IMAGE
            ),

            variant_image_urls=(
                DEMO_VARIANT_IMAGES
            ),

            current_price=Decimal(
                "79.99"
            ),

            original_price=Decimal(
                "99.99"
            ),

            discount_percentage=Decimal(
                "20"
            ),

            rating=Decimal(
                "4.7"
            ),

            reviews_count=66,

            availability="Disponibile",

            seller="AmazonDealsBot Demo",

            ships_from="Amazon",
        )
