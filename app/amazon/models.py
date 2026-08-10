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
    #
    # Non è legata direttamente
    # alla tassonomia Amazon:
    # in futuro il provider farà
    # il mapping.
    category_key: str | None = None

    # Immagine attualmente selezionata.
    #
    # Può essere:
    # - URL
    # - Telegram file_id
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
