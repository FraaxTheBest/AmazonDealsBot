from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from app.amazon.models import ProductSnapshot
from app.config import get_settings


CREATORS_API_BASE = "https://creatorsapi.amazon/catalog/v1"
_API_RATE_LOCK = asyncio.Lock()
_LAST_API_REQUEST_AT = 0.0

DEFAULT_RESOURCES = [
    "images.primary.large",
    "images.primary.medium",
    "images.variants.large",
    "itemInfo.title",
    "itemInfo.byLineInfo",
    "itemInfo.features",
    "itemInfo.classifications",
    "offersV2.listings.availability",
    "offersV2.listings.condition",
    "offersV2.listings.dealDetails",
    "offersV2.listings.isBuyBoxWinner",
    "offersV2.listings.merchantInfo",
    "offersV2.listings.price",
    "offersV2.listings.type",
    "parentASIN",
]


class CreatorsAPIError(RuntimeError):
    pass


class CreatorsAPIConfigurationError(CreatorsAPIError):
    pass


@dataclass(slots=True)
class _TokenCache:
    token: str | None = None
    expires_at: datetime | None = None

    def valid(self) -> bool:
        if not self.token or self.expires_at is None:
            return False
        return datetime.now(timezone.utc) < self.expires_at


class CreatorsAPIClient:
    """Client HTTP minimale per Amazon Creators API.

    Supporta credenziali EU v2.x (Cognito) e v3.x (Login with Amazon).
    Il token viene mantenuto in memoria e riutilizzato fino a poco prima
    della scadenza.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self._token = _TokenCache()
        self._token_lock = asyncio.Lock()

    def configured(self) -> bool:
        return bool(
            self.settings.amazon_creators_client_id
            and self.settings.amazon_creators_client_secret
            and self.settings.amazon_partner_tag.strip()
        )

    def _credentials(self) -> tuple[str, str, str]:
        if not self.configured():
            raise CreatorsAPIConfigurationError(
                "Creators API non configurata. Imposta le credenziali in .env."
            )
        assert self.settings.amazon_creators_client_id is not None
        assert self.settings.amazon_creators_client_secret is not None
        return (
            self.settings.amazon_creators_client_id.get_secret_value(),
            self.settings.amazon_creators_client_secret.get_secret_value(),
            self.settings.amazon_creators_credential_version.strip(),
        )

    def _token_endpoint(self, version: str) -> str:
        if version.startswith("2."):
            return (
                "https://creatorsapi.auth.eu-south-2.amazoncognito.com/"
                "oauth2/token"
            )
        if version.startswith("3."):
            return "https://api.amazon.co.uk/auth/o2/token"
        raise CreatorsAPIConfigurationError(
            "Versione credenziale Creators API non supportata. Usa 2.x o 3.x."
        )

    async def _fetch_access_token(self) -> str:
        client_id, client_secret, version = self._credentials()
        endpoint = self._token_endpoint(version)
        timeout = self.settings.amazon_creators_timeout_seconds

        async with httpx.AsyncClient(timeout=timeout) as client:
            if version.startswith("2."):
                response = await client.post(
                    endpoint,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "creatorsapi/default",
                    },
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                )
            else:
                response = await client.post(
                    endpoint,
                    json={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "creatorsapi::default",
                    },
                    headers={"Content-Type": "application/json"},
                )

        if response.status_code >= 400:
            raise CreatorsAPIError(
                f"Autenticazione Creators API fallita (HTTP {response.status_code})."
            )

        data = response.json()
        token = str(data.get("access_token") or "").strip()
        if not token:
            raise CreatorsAPIError("Creators API non ha restituito access_token.")

        try:
            expires_in = int(data.get("expires_in") or 3600)
        except (TypeError, ValueError):
            expires_in = 3600

        # Margine per evitare di usare token in scadenza durante una richiesta.
        safe_seconds = max(60, expires_in - 90)
        self._token = _TokenCache(
            token=token,
            expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=safe_seconds),
        )
        return token

    async def access_token(self) -> str:
        if self._token.valid():
            assert self._token.token is not None
            return self._token.token

        async with self._token_lock:
            if self._token.valid():
                assert self._token.token is not None
                return self._token.token
            return await self._fetch_access_token()

    async def _post(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = await self.access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-marketplace": self.settings.amazon_marketplace,
        }

        global _LAST_API_REQUEST_AT
        response = None
        for attempt in range(3):
            async with _API_RATE_LOCK:
                minimum = max(0.0, float(self.settings.amazon_min_request_interval_seconds))
                wait_for = minimum - (time.monotonic() - _LAST_API_REQUEST_AT)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)

                async with httpx.AsyncClient(
                    timeout=self.settings.amazon_creators_timeout_seconds
                ) as client:
                    response = await client.post(
                        f"{CREATORS_API_BASE}/{operation}",
                        headers=headers,
                        json=payload,
                    )
                _LAST_API_REQUEST_AT = time.monotonic()

            if response.status_code < 400:
                break
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else float(2 ** attempt)
            except ValueError:
                delay = float(2 ** attempt)
            await asyncio.sleep(max(1.0, min(delay, 30.0)))

        assert response is not None
        if response.status_code >= 400:
            raise CreatorsAPIError(
                f"Creators API {operation} fallita (HTTP {response.status_code})."
            )

        try:
            return response.json()
        except ValueError as exc:
            raise CreatorsAPIError("Risposta Creators API non JSON.") from exc

    async def get_items(
        self,
        asins: list[str] | tuple[str, ...],
        partner_tag: str,
    ) -> list[ProductSnapshot]:
        clean_asins = [asin.strip().upper() for asin in asins if asin.strip()]
        if not clean_asins:
            return []

        payload = {
            "itemIds": clean_asins[:10],
            "itemIdType": "ASIN",
            "marketplace": self.settings.amazon_marketplace,
            "partnerTag": partner_tag,
            "resources": DEFAULT_RESOURCES,
        }
        data = await self._post("getItems", payload)
        raw_items = (
            data.get("itemsResult", {}).get("items", [])
            if isinstance(data, dict)
            else []
        )
        return [
            product
            for item in raw_items
            if (product := self._parse_item(item, category_key=None)) is not None
        ]

    async def search_items(
        self,
        *,
        partner_tag: str,
        keywords: str,
        search_index: str = "All",
        category_key: str | None = None,
        min_saving_percent: int | None = None,
        delivery_flags: list[str] | tuple[str, ...] | None = None,
        item_count: int = 10,
        item_page: int = 1,
    ) -> list[ProductSnapshot]:
        keywords = keywords.strip()
        if not keywords:
            raise ValueError("SearchItems richiede una keyword non vuota.")

        payload: dict[str, Any] = {
            "partnerTag": partner_tag,
            "marketplace": self.settings.amazon_marketplace,
            "keywords": keywords,
            "searchIndex": search_index or "All",
            "itemCount": max(1, min(int(item_count), 10)),
            "itemPage": max(1, min(int(item_page), 10)),
            "languagesOfPreference": ["it_IT"],
            "currencyOfPreference": "EUR",
            "resources": DEFAULT_RESOURCES,
        }
        if min_saving_percent is not None:
            safe_discount = max(1, min(int(min_saving_percent), 99))
            payload["minSavingPercent"] = safe_discount

        if delivery_flags:
            clean_flags = [
                str(value).strip()
                for value in delivery_flags
                if str(value).strip()
            ]
            if clean_flags:
                payload["deliveryFlags"] = clean_flags

        data = await self._post("searchItems", payload)
        raw_items = (
            data.get("searchResult", {}).get("items", [])
            if isinstance(data, dict)
            else []
        )
        return [
            product
            for item in raw_items
            if (product := self._parse_item(item, category_key=category_key))
            is not None
        ]

    async def test_connection(self) -> bool:
        await self.access_token()
        return True

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _display_value(container: Any, key: str) -> str | None:
        if not isinstance(container, dict):
            return None
        value = container.get(key)
        if not isinstance(value, dict):
            return None
        display = value.get("displayValue")
        if display is None:
            return None
        text = str(display).strip()
        return text or None

    def _parse_item(
        self,
        item: Any,
        *,
        category_key: str | None,
    ) -> ProductSnapshot | None:
        if not isinstance(item, dict):
            return None

        asin = str(item.get("asin") or "").strip().upper()
        detail_url = str(item.get("detailPageURL") or "").strip()
        if not asin or not detail_url:
            return None

        item_info = item.get("itemInfo") or {}
        title = self._display_value(item_info, "title") or f"Amazon {asin}"
        byline = item_info.get("byLineInfo") if isinstance(item_info, dict) else {}
        brand = self._display_value(byline, "brand")
        manufacturer = self._display_value(byline, "manufacturer")

        features = item_info.get("features") if isinstance(item_info, dict) else None
        description = None
        if isinstance(features, dict):
            values = features.get("displayValues")
            if isinstance(values, list):
                text_values = [str(x).strip() for x in values if str(x).strip()]
                if text_values:
                    description = " • ".join(text_values[:3])[:1200]

        images = item.get("images") or {}
        primary = images.get("primary") if isinstance(images, dict) else {}
        primary_url = None
        if isinstance(primary, dict):
            for size in ("large", "medium", "small"):
                data = primary.get(size)
                if isinstance(data, dict) and data.get("url"):
                    primary_url = str(data["url"])
                    break

        variant_urls: list[str] = []
        variants = images.get("variants") if isinstance(images, dict) else None
        if isinstance(variants, list):
            for variant in variants:
                if not isinstance(variant, dict):
                    continue
                for size in ("large", "medium", "small"):
                    data = variant.get(size)
                    if isinstance(data, dict) and data.get("url"):
                        url = str(data["url"])
                        if url not in variant_urls:
                            variant_urls.append(url)
                        break

        listings = (
            (item.get("offersV2") or {}).get("listings", [])
            if isinstance(item.get("offersV2") or {}, dict)
            else []
        )
        listing: dict[str, Any] = {}
        if isinstance(listings, list) and listings:
            buybox = next(
                (
                    row
                    for row in listings
                    if isinstance(row, dict) and row.get("isBuyBoxWinner") is True
                ),
                None,
            )
            first = next((row for row in listings if isinstance(row, dict)), None)
            listing = buybox or first or {}

        price = listing.get("price") if isinstance(listing, dict) else {}
        money = price.get("money") if isinstance(price, dict) else {}
        saving_basis = price.get("savingBasis") if isinstance(price, dict) else {}
        saving_money = (
            saving_basis.get("money") if isinstance(saving_basis, dict) else {}
        )
        savings = price.get("savings") if isinstance(price, dict) else {}

        current_price = self._decimal(
            money.get("amount") if isinstance(money, dict) else None
        )
        original_price = self._decimal(
            saving_money.get("amount")
            if isinstance(saving_money, dict)
            else None
        )
        saving_basis_type = (
            str(saving_basis.get("savingBasisType") or "").strip().upper()
            if isinstance(saving_basis, dict)
            else ""
        )
        lowest_price = (
            original_price if "LOWEST" in saving_basis_type else None
        )
        discount = self._decimal(
            savings.get("percentage") if isinstance(savings, dict) else None
        )

        availability_data = listing.get("availability") or {}
        availability_type = (
            str(availability_data.get("type") or "").strip().upper()
            if isinstance(availability_data, dict)
            else ""
        )
        available_types = {"IN_STOCK", "INSTOCK", "INSTOCKSCARCE", "PREORDER"}
        availability = (
            "Disponibile"
            if availability_type in available_types
            else (availability_type or None)
        )

        merchant = listing.get("merchantInfo") or {}
        seller = (
            str(merchant.get("name") or "").strip() or None
            if isinstance(merchant, dict)
            else None
        )

        condition_data = listing.get("condition") or {}
        condition = (
            str(condition_data.get("value") or "").strip() or None
            if isinstance(condition_data, dict)
            else None
        )

        deal = listing.get("dealDetails") or {}
        badge = (
            str(deal.get("badge") or "").strip() or None
            if isinstance(deal, dict)
            else None
        )
        access_type = (
            str(deal.get("accessType") or "").strip().upper()
            if isinstance(deal, dict)
            else ""
        )
        deal_ends_at = None
        if isinstance(deal, dict) and deal.get("endTime"):
            try:
                deal_ends_at = datetime.fromisoformat(
                    str(deal["endTime"]).replace("Z", "+00:00")
                )
            except ValueError:
                deal_ends_at = None

        raw_offer_type = str(listing.get("type") or "").strip().upper()
        if "LIGHTNING" in raw_offer_type:
            offer_type = "lightning"
        elif lowest_price is not None:
            offer_type = "lowest"
        elif condition and condition.lower() in {"used", "refurbished"}:
            offer_type = "warehouse"
        else:
            # OffersV2 non espone un segnale universale "coupon".
            # Non lo inventiamo.
            offer_type = "normal"

        is_prime = (
            True
            if access_type in {"PRIME_EXCLUSIVE", "PRIMEEARLYACCESS"}
            else None
        )

        return ProductSnapshot(
            asin=asin,
            title=title,
            detail_url=detail_url,
            affiliate_url=detail_url,
            brand=brand,
            manufacturer=manufacturer,
            category_key=category_key,
            offer_type=offer_type,
            source_updated_at=datetime.now(timezone.utc),
            image_url=primary_url,
            primary_image_url=primary_url,
            variant_image_urls=variant_urls,
            current_price=current_price,
            original_price=original_price,
            discount_percentage=discount,
            lowest_price=lowest_price,
            currency="EUR",
            availability=availability,
            condition=condition,
            seller=seller,
            # OffersV2 non fornisce più DeliveryInfo/FBA in modo equivalente.
            ships_from=None,
            fulfiller=None,
            is_prime=is_prime,
            coupon_text=None,
            deal_badge=badge,
            deal_ends_at=deal_ends_at,
            description=description,
        )
