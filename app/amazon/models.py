from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class ProductSnapshot(BaseModel):
    asin: str
    title: str
    detail_url: str

    affiliate_url: str | None = None
    affiliate_short_url: str | None = None

    brand: str | None = None
    manufacturer: str | None = None

    category_key: str | None = None
    category: str | None = None
    subcategory: str | None = None

    # Metadato normalizzato dal provider.
    # Valori usati dal ranking:
    # lightning, coupon, lowest, warehouse, normal, error.
    offer_type: str | None = None

    source_updated_at: datetime | None = None

    image_url: str | None = None
    primary_image_url: str | None = None
    variant_image_urls: list[str] = Field(default_factory=list)

    current_price: Decimal | None = None
    original_price: Decimal | None = None
    discount_percentage: Decimal | None = None
    lowest_price: Decimal | None = None
    currency: str = "EUR"

    rating: Decimal | None = None
    reviews_count: int | None = None

    availability: str | None = None
    condition: str | None = None
    seller: str | None = None
    ships_from: str | None = None
    fulfiller: str | None = None

    is_prime: bool | None = None
    coupon_text: str | None = None
    deal_badge: str | None = None
    deal_ends_at: datetime | None = None

    description: str | None = None

    # Campi liberi per template personalizzati.
    custom: str | None = None
    custom1: str | None = None
    custom2: str | None = None

    # Campi opzionali prodotti dal modulo AI.
    ai_title: str | None = None
    ai_description: str | None = None
    ai_emoji: str | None = None
