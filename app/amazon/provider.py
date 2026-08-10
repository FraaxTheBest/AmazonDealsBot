"""Facade compatibile con il codice storico.

Il nome MockAmazonProvider viene mantenuto per non rompere app/posts.py,
ma da questa fase delega al provider configurato in .env.
"""

from typing import Protocol

from app.amazon.models import ProductSnapshot
from app.amazon.provider_factory import DemoProvider, get_provider
from app.config import get_settings


class AmazonProvider(Protocol):
    async def get_product(self, asin: str) -> ProductSnapshot:
        ...


class MockAmazonProvider:
    async def get_product(self, asin: str) -> ProductSnapshot:
        settings = get_settings()
        provider = get_provider()
        # Compatibilità manuale: usa il tag globale. La patch finale di posts.py
        # passa invece dal tag specifico del canale quando disponibile.
        return await provider.get_product(asin, settings.amazon_partner_tag)


# Esposto anche con un nome più corretto per nuovo codice.
ConfiguredAmazonProvider = MockAmazonProvider

__all__ = [
    "AmazonProvider",
    "MockAmazonProvider",
    "ConfiguredAmazonProvider",
    "DemoProvider",
]
