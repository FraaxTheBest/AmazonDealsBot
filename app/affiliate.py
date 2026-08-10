from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import httpx

from app.amazon.models import ProductSnapshot


@dataclass(slots=True)
class AffiliateDecision:
    status: str
    detected_partner_tag: str | None = None
    warning: str | None = None


def is_amzn_short_url(
    value: str,
) -> bool:
    try:
        parsed = urlparse(
            value.strip()
        )

    except ValueError:
        return False

    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    return (
        parsed.scheme in {
            "http",
            "https",
        }
        and hostname in {
            "amzn.to",
            "www.amzn.to",
        }
    )


def is_amazon_it_url(
    value: str,
) -> bool:
    try:
        parsed = urlparse(
            value.strip()
        )

    except ValueError:
        return False

    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    return (
        hostname == "amazon.it"
        or hostname.endswith(
            ".amazon.it"
        )
    )


def extract_partner_tag(
    value: str,
) -> str | None:
    """
    Legge ?tag=... da un URL Amazon.
    """

    try:
        parsed = urlparse(value)

    except ValueError:
        return None

    query = parse_qs(
        parsed.query
    )

    tags = query.get(
        "tag"
    )

    if not tags:
        return None

    tag = tags[0].strip()

    return tag or None


async def resolve_short_url(
    value: str,
) -> str | None:
    """
    Segue esclusivamente redirect amzn.to.

    Accetta il risultato solo se
    termina su Amazon.it.
    """

    if not is_amzn_short_url(
        value
    ):
        return None

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
            response = await client.get(
                value.strip()
            )

        final_url = str(
            response.url
        )

    except httpx.HTTPError:
        return None

    if not is_amazon_it_url(
        final_url
    ):
        return None

    return final_url


def affiliate_admin_text(
    decision: AffiliateDecision,
) -> str:
    if (
        decision.status
        == "short_verified"
    ):
        return (
            "🔐 <b>Affiliate Engine</b>\n"
            "✅ Shortlink amzn.to "
            "verificato\n"
            f"🏷 Tag: "
            f"<code>"
            f"{decision.detected_partner_tag}"
            f"</code>"
        )

    if (
        decision.status
        == "short_unverified"
    ):
        return (
            "🔐 <b>Affiliate Engine</b>\n"
            "⚠️ Shortlink amzn.to "
            "mantenuto\n"
            "Tag non leggibile dal "
            "redirect."
        )

    if (
        decision.status
        == "short_rejected"
    ):
        return (
            "🔐 <b>Affiliate Engine</b>\n"
            "⚠️ Lo shortlink conteneva "
            "un Tracking ID diverso.\n"
            "✅ Sto usando il link "
            "affiliato del provider."
        )

    if (
        decision.status
        == "provider"
    ):
        text = (
            "🔐 <b>Affiliate Engine</b>\n"
            "✅ Link affiliato "
            "del provider"
        )

        if (
            decision.detected_partner_tag
        ):
            text += (
                "\n🏷 Tag: "
                "<code>"
                f"{decision.detected_partner_tag}"
                "</code>"
            )

        return text

    return (
        "🔐 <b>Affiliate Engine</b>\n"
        "❌ Nessun link affiliato "
        "disponibile."
    )


async def apply_affiliate_link(
    product: ProductSnapshot,
    submitted_value: str,
    expected_partner_tag: str,
) -> tuple[
    ProductSnapshot,
    AffiliateDecision,
]:
    """
    Decide quale link deve essere
    utilizzato nel post.
    """

    submitted_value = (
        submitted_value.strip()
    )

    #
    # CASO 1:
    # l'utente inserisce amzn.to
    #
    if is_amzn_short_url(
        submitted_value
    ):
        resolved_url = (
            await resolve_short_url(
                submitted_value
            )
        )

        detected_tag = None

        if resolved_url:
            detected_tag = (
                extract_partner_tag(
                    resolved_url
                )
            )

        #
        # Tag trovato ed è il nostro.
        #
        if (
            detected_tag
            == expected_partner_tag
        ):
            product = (
                product.model_copy(
                    update={
                        "affiliate_short_url":
                            submitted_value
                    }
                )
            )

            return (
                product,
                AffiliateDecision(
                    status=(
                        "short_verified"
                    ),
                    detected_partner_tag=(
                        detected_tag
                    ),
                ),
            )

        #
        # Tag trovato ma appartiene
        # a un altro tracking ID.
        #
        if (
            detected_tag
            and detected_tag
            != expected_partner_tag
        ):
            product = (
                product.model_copy(
                    update={
                        "affiliate_short_url":
                            None
                    }
                )
            )

            if product.affiliate_url:
                return (
                    product,
                    AffiliateDecision(
                        status=(
                            "short_rejected"
                        ),
                        detected_partner_tag=(
                            detected_tag
                        ),
                        warning=(
                            "Tracking ID "
                            "differente."
                        ),
                    ),
                )

            return (
                product,
                AffiliateDecision(
                    status=(
                        "non_affiliate"
                    ),
                    detected_partner_tag=(
                        detected_tag
                    ),
                    warning=(
                        "Tracking ID "
                        "differente."
                    ),
                ),
            )

        #
        # Non siamo riusciti a leggere
        # il tag dal redirect.
        #
        # Manteniamo comunque lo
        # shortlink fornito manualmente,
        # ma lo segnaliamo come
        # non verificato.
        #
        product = product.model_copy(
            update={
                "affiliate_short_url":
                    submitted_value
            }
        )

        return (
            product,
            AffiliateDecision(
                status=(
                    "short_unverified"
                ),
            ),
        )

    #
    # CASO 2:
    # ASIN / normale URL Amazon.
    #
    # Il provider decide il link.
    #
    if product.affiliate_url:
        detected_tag = (
            extract_partner_tag(
                product.affiliate_url
            )
        )

        return (
            product,
            AffiliateDecision(
                status="provider",
                detected_partner_tag=(
                    detected_tag
                ),
            ),
        )

    #
    # CASO 3:
    # nessun link affiliato.
    #
    return (
        product,
        AffiliateDecision(
            status="non_affiliate"
        ),
    )
