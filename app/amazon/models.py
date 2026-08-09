from decimal import Decimal

from pydantic import BaseModel


class ProductSnapshot(BaseModel):
    asin: str
    title: str
    detail_url: str

    brand: str | None = None
    image_url: str | None = None

    current_price: Decimal | None = None
    original_price: Decimal | None = None
    discount_percentage: Decimal | None = None

    currency: str = "EUR"
    availability: str | None = None
