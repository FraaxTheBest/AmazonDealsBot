import re
from urllib.parse import urlparse

import httpx


ASIN_PATTERN = re.compile(
    r"^[A-Z0-9]{10}$",
    re.IGNORECASE,
)

URL_PATTERNS = [
    re.compile(
        r"/dp/([A-Z0-9]{10})(?:[/?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"/gp/product/([A-Z0-9]{10})(?:[/?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"/gp/aw/d/([A-Z0-9]{10})(?:[/?]|$)",
        re.IGNORECASE,
    ),
]


def extract_asin_from_amazon_url(
    value: str,
) -> str | None:
    """Estrae l'ASIN da un normale URL Amazon."""

    try:
        parsed = urlparse(value)
    except ValueError:
        return None

    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    if not (
        hostname == "amazon.it"
        or hostname.endswith(".amazon.it")
    ):
        return None

    for pattern in URL_PATTERNS:
        match = pattern.search(parsed.path)

        if match:
            return match.group(1).upper()

    return None


async def extract_asin(
    value: str,
) -> str | None:
    """
    Estrae un ASIN da:
    - ASIN puro
    - URL amazon.it
    - short link amzn.to
    """

    value = value.strip()

    # ASIN puro
    if ASIN_PATTERN.fullmatch(value):
        return value.upper()

    try:
        parsed = urlparse(value)
    except ValueError:
        return None

    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    # Normale URL Amazon.it
    if (
        hostname == "amazon.it"
        or hostname.endswith(".amazon.it")
    ):
        return extract_asin_from_amazon_url(value)

    # Link corto Amazon
    if hostname in {"amzn.to", "www.amzn.to"}:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=10.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "AmazonDealsBot/1.0"
                    )
                },
            ) as client:
                response = await client.get(value)

            final_url = str(response.url)

            return extract_asin_from_amazon_url(
                final_url
            )

        except httpx.HTTPError:
            return None

    return None
