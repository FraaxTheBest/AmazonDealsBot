from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

from app.amazon.category_mapping import category_to_search_index
from app.amazon.creators_api import CreatorsAPIClient
from app.amazon.models import ProductSnapshot
from app.autopost_store import get_or_create_autopost_config, get_selected_categories
from app.config import get_settings
from app.affiliate_store import get_effective_partner_tag


@dataclass(frozen=True, slots=True)
class ProviderBatch:
    provider_name: str
    products: tuple[ProductSnapshot, ...]


class ProductProvider(Protocol):
    async def get_product(self, asin: str, partner_tag: str) -> ProductSnapshot:
        ...

    async def scan_channel(
        self,
        owner_telegram_user_id: int,
        channel_id: int,
    ) -> ProviderBatch:
        ...


class DemoProvider:
    name = "demo"

    @staticmethod
    def _products(partner_tag: str) -> list[ProductSnapshot]:
        now = datetime.now(timezone.utc)

        def url(asin: str) -> str:
            return f"https://www.amazon.it/dp/{asin}?tag={partner_tag}"

        return [
            ProductSnapshot(
                asin="B0DEMO0001",
                title="DEMO - Smartphone offerta eccellente",
                detail_url="https://www.amazon.it/dp/B0DEMO0001",
                affiliate_url=url("B0DEMO0001"),
                brand="DemoTech",
                category_key="electronics",
                offer_type="lightning",
                source_updated_at=now,
                current_price=Decimal("69.99"),
                original_price=Decimal("99.99"),
                discount_percentage=Decimal("30"),
                rating=Decimal("4.8"),
                reviews_count=1200,
                availability="Disponibile",
                seller="Amazon",
                ships_from="Amazon",
                is_prime=True,
                deal_badge="Offerta Lampo",
            ),
            ProductSnapshot(
                asin="B0DEMO0002",
                title="DEMO - Casa e cucina offerta buona",
                detail_url="https://www.amazon.it/dp/B0DEMO0002",
                affiliate_url=url("B0DEMO0002"),
                brand="CasaDemo",
                category_key="home_kitchen",
                offer_type="coupon",
                source_updated_at=now - timedelta(minutes=3),
                current_price=Decimal("79.99"),
                original_price=Decimal("99.99"),
                discount_percentage=Decimal("20"),
                rating=Decimal("4.7"),
                reviews_count=66,
                availability="Disponibile",
                seller="Negozio Demo",
                ships_from="Amazon",
                coupon_text="Coupon DEMO",
            ),
            ProductSnapshot(
                asin="B0DEMO0003",
                title="DEMO - Elettronica sconto basso",
                detail_url="https://www.amazon.it/dp/B0DEMO0003",
                affiliate_url=url("B0DEMO0003"),
                brand="DemoTech",
                category_key="electronics",
                offer_type="lowest",
                source_updated_at=now - timedelta(minutes=6),
                current_price=Decimal("94.99"),
                original_price=Decimal("99.99"),
                discount_percentage=Decimal("5"),
                rating=Decimal("4.8"),
                reviews_count=800,
                availability="Disponibile",
                seller="Amazon",
                ships_from="Amazon",
            ),
            ProductSnapshot(
                asin="B0DEMO0004",
                title="DEMO - Sport non disponibile",
                detail_url="https://www.amazon.it/dp/B0DEMO0004",
                affiliate_url=url("B0DEMO0004"),
                category_key="sports",
                offer_type="normal",
                source_updated_at=now - timedelta(minutes=9),
                current_price=Decimal("49.99"),
                original_price=Decimal("99.99"),
                discount_percentage=Decimal("50"),
                rating=Decimal("4.9"),
                reviews_count=3000,
                availability="Non disponibile",
                seller="Amazon",
                ships_from="Amazon",
            ),
            ProductSnapshot(
                asin="B0DEMO0005",
                title="DEMO - Casa prezzo mancante",
                detail_url="https://www.amazon.it/dp/B0DEMO0005",
                affiliate_url=url("B0DEMO0005"),
                category_key="home_kitchen",
                offer_type="normal",
                source_updated_at=now - timedelta(minutes=12),
                current_price=None,
                original_price=Decimal("99.99"),
                discount_percentage=None,
                rating=Decimal("4.6"),
                reviews_count=350,
                availability="Disponibile",
                seller="Amazon",
                ships_from="Amazon",
            ),
        ]

    async def get_product(self, asin: str, partner_tag: str) -> ProductSnapshot:
        normalized = asin.strip().upper()
        for product in self._products(partner_tag):
            if product.asin == normalized:
                return product
        return ProductSnapshot(
            asin=normalized,
            title=f"Prodotto Amazon di test ({normalized})",
            detail_url=f"https://www.amazon.it/dp/{normalized}",
            affiliate_url=(
                f"https://www.amazon.it/dp/{normalized}?tag={partner_tag}"
            ),
            brand="AmazonDealsBot Demo",
            offer_type="normal",
            source_updated_at=datetime.now(timezone.utc),
            current_price=Decimal("79.99"),
            original_price=Decimal("99.99"),
            discount_percentage=Decimal("20"),
            rating=Decimal("4.7"),
            reviews_count=66,
            availability="Disponibile",
            seller="AmazonDealsBot Demo",
            ships_from="Amazon",
        )

    async def scan_channel(
        self,
        owner_telegram_user_id: int,
        channel_id: int,
    ) -> ProviderBatch:
        tag = await get_effective_partner_tag(owner_telegram_user_id, channel_id)
        return ProviderBatch(self.name, tuple(self._products(tag)))


class CreatorsProvider:
    name = "creators"

    def __init__(self) -> None:
        self.client = CreatorsAPIClient()

    async def get_product(self, asin: str, partner_tag: str) -> ProductSnapshot:
        products = await self.client.get_items([asin], partner_tag=partner_tag)
        if not products:
            raise ValueError("Prodotto non trovato tramite Creators API.")
        return products[0]

    async def scan_channel(
        self,
        owner_telegram_user_id: int,
        channel_id: int,
    ) -> ProviderBatch:
        settings = get_settings()
        config = await get_or_create_autopost_config(
            owner_telegram_user_id,
            channel_id,
        )
        selected = get_selected_categories(config)
        categories = list(selected) if selected else [
            "electronics",
            "home_kitchen",
            "computers",
            "beauty",
            "sports",
            "garden",
            "toys",
            "fashion",
            "automotive",
            "books",
            "pets",
            "grocery",
            "health",
        ]
        # Ruotiamo le categorie tra scansioni invece di interrogare sempre
        # le prime N. Non serve stato DB: l'offset temporale è deterministico
        # e continua a cambiare anche dopo un riavvio.
        per_run = max(1, min(settings.amazon_scan_categories_per_run, len(categories)))
        if categories:
            minute_bucket = int(datetime.now(timezone.utc).timestamp() // 60)
            offset = (minute_bucket + int(channel_id)) % len(categories)
            categories = [
                categories[(offset + index) % len(categories)]
                for index in range(per_run)
            ]

        keywords = [
            value.strip()
            for value in settings.amazon_search_keywords.split(",")
            if value.strip()
        ] or ["offerta"]

        tag = await get_effective_partner_tag(owner_telegram_user_id, channel_id)
        min_discount = None
        try:
            raw = int(Decimal(str(config.min_discount_percentage)))
            if raw > 0:
                min_discount = min(raw, 99)
        except Exception:
            min_discount = None

        products: list[ProductSnapshot] = []
        seen: set[str] = set()

        for index, category in enumerate(categories):
            keyword = keywords[index % len(keywords)]
            batch = await self.client.search_items(
                partner_tag=tag,
                keywords=keyword,
                search_index=category_to_search_index(category),
                category_key=category,
                min_saving_percent=min_discount,
                delivery_flags=(
                    ["FulfilledByAmazon"]
                    if config.require_amazon_shipping
                    else None
                ),
                item_count=settings.amazon_search_item_count,
            )
            for product in batch:
                if config.require_amazon_shipping:
                    # SearchItems ha già applicato il filtro ufficiale FBA.
                    # Registriamo il fatto verificato nel modello così il
                    # filtro locale non lo scarta per dato DeliveryInfo assente.
                    product = product.model_copy(
                        update={
                            "ships_from": "Amazon",
                            "fulfiller": "Amazon",
                        }
                    )
                asin = product.asin.strip().upper()
                if asin in seen:
                    continue
                seen.add(asin)
                products.append(product)

        return ProviderBatch(self.name, tuple(products))


_PROVIDER_CACHE: dict[str, ProductProvider] = {}


def get_provider() -> ProductProvider:
    settings = get_settings()
    name = settings.amazon_provider
    provider = _PROVIDER_CACHE.get(name)
    if provider is None:
        provider = CreatorsProvider() if name == "creators" else DemoProvider()
        _PROVIDER_CACHE[name] = provider
    return provider


async def get_channel_products(
    owner_telegram_user_id: int,
    channel_id: int,
) -> ProviderBatch:
    return await get_provider().scan_channel(owner_telegram_user_id, channel_id)


async def get_product_for_channel(
    asin: str,
    owner_telegram_user_id: int,
    channel_id: int,
) -> ProductSnapshot:
    tag = await get_effective_partner_tag(owner_telegram_user_id, channel_id)
    return await get_provider().get_product(asin, tag)


async def refresh_product(
    product: ProductSnapshot,
    owner_telegram_user_id: int | None = None,
    channel_id: int | None = None,
) -> ProductSnapshot:
    settings = get_settings()
    if settings.amazon_provider != "creators":
        return product

    if owner_telegram_user_id is not None and channel_id is not None:
        tag = await get_effective_partner_tag(owner_telegram_user_id, channel_id)
    else:
        tag = settings.amazon_partner_tag

    provider = get_provider()
    refreshed = await provider.get_product(product.asin, tag)

    # Manteniamo eventuali customizzazioni locali dell'immagine e campi custom.
    return refreshed.model_copy(
        update={
            "image_url": product.image_url or refreshed.image_url,
            "custom": product.custom,
            "custom1": product.custom1,
            "custom2": product.custom2,
        }
    )
