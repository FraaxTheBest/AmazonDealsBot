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

    # Categoria interna del bot.
    category_key: str | None = None

    # Metadato opzionale del provider.
    # Valori supportati dalla Fase 11:
    # lightning, coupon, lowest,
    # warehouse, normal, error.
    #
    # Se il provider non lo fornisce,
    # il prodotto viene trattato come normal.
    offer_type: str | None = None

    # Timestamp opzionale del provider.
    # Utilizzato dall'ordinamento "più recente".
    source_updated_at: datetime | None = None

    # Immagine attualmente selezionata.
    image_url: str | None = None

    primary_image_url: str | None = None

    variant_image_urls: list[str] = Field(
        default_factory=list
    )

    current_price: Decimal | None = None

    original_price: Decimal | None = None

    discount_percentage: Decimal | None = None

    currency: str = "EUR"

    rating: Decimal | None = None

    reviews_count: int | None = None

    availability: str | None = None

    seller: str | None = None

    ships_from: str | None = None
