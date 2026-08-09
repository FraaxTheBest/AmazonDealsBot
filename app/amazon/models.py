from decimal import Decimal

from pydantic import BaseModel


class ProductSnapshot(BaseModel):
    asin: str
    title: str
    detail_url: str

    affiliate_url: str | None = None
    affiliate_short_url: str | None = None

    brand: str | None = None
    image_url: str | None = None

    current_price: Decimal | None = None
    original_price: Decimal | None = None
    discount_percentage: Decimal | None = None

    currency: str = "EUR"

    rating: Decimal | None = None
    reviews_count: int | None = None

    availability: str | None = None

    seller: str | None = None
    ships_from: str | None = None
