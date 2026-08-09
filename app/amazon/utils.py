import re
from urllib.parse import urlparse


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


def extract_asin(value: str) -> str | None:
    """Estrae un ASIN da ASIN puro o URL Amazon.it."""

    value = value.strip()

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
