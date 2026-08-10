from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from app.ai_store import get_or_create_ai_config
from app.amazon.models import ProductSnapshot
from app.config import get_settings


@dataclass(frozen=True, slots=True)
class AIEnhancementResult:
    used_ai: bool
    product: ProductSnapshot
    error_message: str | None = None


def ai_available() -> bool:
    settings = get_settings()
    return bool(settings.openai_api_key)


def _extract_json(text: str) -> dict:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*```$", "", clean)
    start = clean.find("{")
    end = clean.rfind("}")
    if start >= 0 and end > start:
        clean = clean[start : end + 1]
    value = json.loads(clean)
    if not isinstance(value, dict):
        raise ValueError("Output AI non valido.")
    return value


async def enhance_product_with_ai(
    owner_telegram_user_id: int,
    product: ProductSnapshot,
) -> AIEnhancementResult:
    config = await get_or_create_ai_config(owner_telegram_user_id)
    settings = get_settings()

    if not config.enabled:
        return AIEnhancementResult(False, product)

    if not settings.openai_api_key:
        return AIEnhancementResult(
            False,
            product,
            "AI attiva ma OPENAI_API_KEY non configurata.",
        )

    prompt = (
        "Rispondi SOLO con JSON valido con chiavi title, description, emoji. "
        "Stai preparando un post Telegram italiano per un prodotto Amazon. "
        "Non inventare prezzo, sconto, coupon, caratteristiche o promesse. "
        f"Accorcia il titolo a massimo {int(config.max_title_chars)} caratteri. "
        "La descrizione deve essere breve, neutra e basata solo sui dati forniti. "
        "Scegli una singola emoji coerente.\n\n"
        f"Titolo originale: {product.title}\n"
        f"Brand: {product.brand or ''}\n"
        f"Descrizione/feature: {product.description or ''}\n"
        f"Categoria: {product.category_key or ''}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.ai_timeout_seconds,
        )

        def _call():
            return client.responses.create(
                model=config.model or settings.openai_model,
                input=prompt,
            )

        response = await asyncio.to_thread(_call)
        data = _extract_json(response.output_text)

        title = str(data.get("title") or "").strip()
        description = str(data.get("description") or "").strip()
        emoji = str(data.get("emoji") or "").strip()

        updated = product.model_copy(
            update={
                "ai_title": title or None,
                "ai_description": description or None,
                "ai_emoji": emoji[:12] or None,
            }
        )
        return AIEnhancementResult(True, updated)

    except Exception as exc:
        return AIEnhancementResult(
            False,
            product,
            str(exc)[:300],
        )
