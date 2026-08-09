from decimal import Decimal
from typing import Protocol

from app.amazon.models import ProductSnapshot


class AmazonProvider(Protocol):
    async def get_product(
        self,
        asin: str,
    ) -> ProductSnapshot:
        ...


class MockAmazonProvider:
    """Provider finto usato durante lo sviluppo."""

    async def get_product(
        self,
        asin: str,
    ) -> ProductSnapshot:
        return ProductSnapshot(
            asin=asin,
            title=(
                "Prodotto Amazon di test "
                f"({asin})"
            ),
            brand="AmazonDealsBot Demo",
            detail_url=(
                f"https://www.amazon.it/dp/{asin}"
            ),
            current_price=Decimal("79.99"),
            original_price=Decimal("99.99"),
            discount_percentage=Decimal("20"),
            availability="Disponibile",
        )
