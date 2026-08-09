from decimal import Decimal
from html import escape

from app.amazon.models import ProductSnapshot


DEFAULT_POST_TEMPLATE = (
    "👀 <b>{title}</b>\n\n"
    "{price_line}\n\n"
    "🔎 {link}\n\n"
    "{rating_line}\n"
    "{shipping_line}"
)


def get_public_url(
    product: ProductSnapshot,
) -> str:
    """
    Priorità link:
    1. amzn.to
    2. link affiliato lungo
    3. URL Amazon normale
    """

    return (
        product.affiliate_short_url
        or product.affiliate_url
        or product.detail_url
    )


def format_money(
    value: Decimal | None,
) -> str:
    if value is None:
        return ""

    return (
        f"{value:.2f}"
        .replace(".", ",")
        + "€"
    )


def format_percentage(
    value: Decimal | None,
) -> str:
    if value is None:
        return ""

    if value == value.to_integral():
        return str(int(value))

    return (
        f"{value:.2f}"
        .rstrip("0")
        .rstrip(".")
        .replace(".", ",")
    )


def format_rating(
    value: Decimal | None,
) -> str:
    if value is None:
        return ""

    return f"{value:.1f}"


def format_reviews(
    value: int | None,
) -> str:
    if value is None:
        return ""

    return f"{value:,}".replace(",", ".")


def build_price_line(
    product: ProductSnapshot,
) -> str:
    current_price = format_money(
        product.current_price
    )

    original_price = format_money(
        product.original_price
    )

    discount = format_percentage(
        product.discount_percentage
    )

    if (
        current_price
        and original_price
        and discount
    ):
        return (
            "💰 A soli "
            f"<b>{current_price}</b> "
            f"invece di "
            f"<s>{original_price}</s> "
            f"(-{discount}%)"
        )

    if current_price and original_price:
        return (
            "💰 A soli "
            f"<b>{current_price}</b> "
            f"invece di "
            f"<s>{original_price}</s>"
        )

    if current_price:
        return (
            "💰 A soli "
            f"<b>{current_price}</b>"
        )

    return ""


def build_rating_line(
    product: ProductSnapshot,
) -> str:
    rating = format_rating(
        product.rating
    )

    reviews = format_reviews(
        product.reviews_count
    )

    if rating and reviews:
        return (
            f"⭐ {reviews} Recensioni: "
            f"{rating} / 5.0"
        )

    if rating:
        return (
            f"⭐ Valutazione: "
            f"{rating} / 5.0"
        )

    if reviews:
        return (
            f"⭐ {reviews} Recensioni"
        )

    return ""


def build_shipping_line(
    product: ProductSnapshot,
) -> str:
    seller = product.seller
    ships_from = product.ships_from

    if seller and ships_from:
        seller_clean = escape(seller)
        ships_clean = escape(ships_from)

        if (
            seller.lower() == "amazon"
            and ships_from.lower() == "amazon"
        ):
            return (
                "📦 Venduto e spedito "
                "da Amazon"
            )

        return (
            f"📦 Venduto da {seller_clean} "
            f"e spedito da {ships_clean}"
        )

    if seller:
        return (
            "📦 Venduto da "
            f"{escape(seller)}"
        )

    if ships_from:
        return (
            "📦 Spedito da "
            f"{escape(ships_from)}"
        )

    return ""


def build_template_context(
    product: ProductSnapshot,
) -> dict[str, str]:
    public_url = get_public_url(
        product
    )

    return {
        "title": escape(product.title),
        "brand": escape(
            product.brand or ""
        ),
        "asin": product.asin,
        "price": format_money(
            product.current_price
        ),
        "original_price": format_money(
            product.original_price
        ),
        "discount": format_percentage(
            product.discount_percentage
        ),
        "link": escape(
            public_url,
            quote=False,
        ),
        "rating": format_rating(
            product.rating
        ),
        "reviews": format_reviews(
            product.reviews_count
        ),
        "availability": escape(
            product.availability or ""
        ),
        "seller": escape(
            product.seller or ""
        ),
        "ships_from": escape(
            product.ships_from or ""
        ),
        "price_line": build_price_line(
            product
        ),
        "rating_line": build_rating_line(
            product
        ),
        "shipping_line": build_shipping_line(
            product
        ),
    }


def clean_rendered_template(
    text: str,
) -> str:
    """
    Rimuove righe vuote duplicate create
    dai campi opzionali mancanti.
    """

    result: list[str] = []

    for line in text.splitlines():
        line = line.rstrip()

        if (
            not line
            and result
            and not result[-1]
        ):
            continue

        result.append(line)

    return "\n".join(result).strip()


def render_template(
    template: str,
    product: ProductSnapshot,
) -> str:
    context = build_template_context(
        product
    )

    try:
        rendered = template.format_map(
            context
        )

    except KeyError as exc:
        missing = exc.args[0]

        raise ValueError(
            "Placeholder template "
            f"non valido: {{{missing}}}"
        ) from exc

    return clean_rendered_template(
        rendered
    )


def render_post(
    product: ProductSnapshot,
) -> str:
    return render_template(
        DEFAULT_POST_TEMPLATE,
        product,
    )
