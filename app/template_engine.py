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


class TemplateField:
    """Valore template con modificatori semplici.

    Testo: {title:20} -> massimo 20 caratteri.
    Denaro: {price:0}, {price:2} -> numero di decimali.
    """

    def __init__(self, text: str, *, money_value: Decimal | None = None) -> None:
        self.text = text
        self.money_value = money_value

    def __format__(self, spec: str) -> str:
        spec = (spec or "").strip()
        if not spec:
            return self.text
        try:
            amount = int(spec)
        except ValueError:
            return self.text

        if self.money_value is not None:
            amount = max(0, min(amount, 6))
            return format_money(self.money_value, decimals=amount)

        if amount <= 0 or len(self.text) <= amount:
            return self.text if amount != 0 else ""
        if amount <= 1:
            return self.text[:amount]
        return self.text[: amount - 1].rstrip() + "…"

    def __str__(self) -> str:
        return self.text


def get_public_url(product: ProductSnapshot) -> str:
    return product.affiliate_short_url or product.affiliate_url or product.detail_url


def format_money(value: Decimal | None, decimals: int = 2) -> str:
    if value is None:
        return ""
    decimals = max(0, min(int(decimals), 6))
    return f"{value:.{decimals}f}".replace(".", ",") + "€"


def format_percentage(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == value.to_integral():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def format_rating(value: Decimal | None) -> str:
    return "" if value is None else f"{value:.1f}"


def format_reviews(value: int | None) -> str:
    return "" if value is None else f"{value:,}".replace(",", ".")


def saved_amount(product: ProductSnapshot) -> Decimal | None:
    if product.current_price is None or product.original_price is None:
        return None
    value = product.original_price - product.current_price
    return value if value > 0 else None


def build_price_line(product: ProductSnapshot) -> str:
    current = format_money(product.current_price)
    original = format_money(product.original_price)
    discount = format_percentage(product.discount_percentage)
    if current and original and discount:
        return f"💰 A soli <b>{current}</b> invece di <s>{original}</s> (-{discount}%)"
    if current and original:
        return f"💰 A soli <b>{current}</b> invece di <s>{original}</s>"
    if current:
        return f"💰 A soli <b>{current}</b>"
    return ""


def build_rating_line(product: ProductSnapshot) -> str:
    rating = format_rating(product.rating)
    reviews = format_reviews(product.reviews_count)
    if rating and reviews:
        return f"⭐ {reviews} Recensioni: {rating} / 5.0"
    if rating:
        return f"⭐ Valutazione: {rating} / 5.0"
    if reviews:
        return f"⭐ {reviews} Recensioni"
    return ""


def build_shipping_line(product: ProductSnapshot) -> str:
    seller = product.seller
    ships = product.ships_from or product.fulfiller
    if seller and ships:
        if seller.lower() == "amazon" and ships.lower() == "amazon":
            return "📦 Venduto e spedito da Amazon"
        return f"📦 Venduto da {escape(seller)} e spedito da {escape(ships)}"
    if seller:
        return f"📦 Venduto da {escape(seller)}"
    if ships:
        return f"📦 Spedito da {escape(ships)}"
    return ""


def _text(value) -> str:
    return escape(str(value), quote=False) if value not in (None, "") else ""


def _money(value: Decimal | None) -> TemplateField:
    return TemplateField(format_money(value), money_value=value)


def build_template_context(product: ProductSnapshot) -> dict[str, TemplateField]:
    public_url = get_public_url(product)
    saving = saved_amount(product)
    prime_text = "Prime" if product.is_prime is True else ""

    raw: dict[str, TemplateField] = {
        "title": TemplateField(_text(product.title)),
        "name": TemplateField(_text(product.title)),
        "brand": TemplateField(_text(product.brand)),
        "manufacturer": TemplateField(_text(product.manufacturer)),
        "asin": TemplateField(_text(product.asin)),
        "price": _money(product.current_price),
        "dealPrice": _money(product.current_price),
        "originalPrice": _money(product.original_price),
        "original_price": _money(product.original_price),
        "savedPrice": _money(saving),
        "lowestPrice": _money(product.lowest_price),
        "discount": TemplateField(format_percentage(product.discount_percentage)),
        "discountPerc": TemplateField(format_percentage(product.discount_percentage)),
        "link": TemplateField(escape(public_url, quote=False)),
        "rating": TemplateField(format_rating(product.rating)),
        "reviews": TemplateField(format_reviews(product.reviews_count)),
        "availability": TemplateField(_text(product.availability)),
        "condition": TemplateField(_text(product.condition)),
        "seller": TemplateField(_text(product.seller)),
        "ships_from": TemplateField(_text(product.ships_from)),
        "fulfiller": TemplateField(_text(product.fulfiller or product.ships_from)),
        "category": TemplateField(_text(product.category or product.category_key)),
        "subcategory": TemplateField(_text(product.subcategory)),
        "prime": TemplateField(prime_text),
        "coupon": TemplateField(_text(product.coupon_text)),
        "description": TemplateField(_text(product.description)),
        "custom": TemplateField(_text(product.custom)),
        "custom1": TemplateField(_text(product.custom1)),
        "custom2": TemplateField(_text(product.custom2)),
        "aiTitle": TemplateField(_text(product.ai_title)),
        "aiDescription": TemplateField(_text(product.ai_description)),
        "aiEmoji": TemplateField(_text(product.ai_emoji)),
        "price_line": TemplateField(build_price_line(product)),
        "rating_line": TemplateField(build_rating_line(product)),
        "shipping_line": TemplateField(build_shipping_line(product)),
    }
    return raw


def clean_rendered_template(text: str) -> str:
    result: list[str] = []
    for line in text.splitlines():
        line = line.rstrip()
        # Elimina righe composte solo da spazi/separatori HTML vuoti.
        if not line and result and not result[-1]:
            continue
        result.append(line)
    return "\n".join(result).strip()


def render_template(template: str, product: ProductSnapshot) -> str:
    context = build_template_context(product)
    try:
        rendered = template.format_map(context)
    except KeyError as exc:
        raise ValueError(f"Placeholder template non valido: {{{exc.args[0]}}}") from exc
    except ValueError as exc:
        raise ValueError(f"Formato placeholder non valido: {exc}") from exc
    return clean_rendered_template(rendered)


def render_post(product: ProductSnapshot) -> str:
    return render_template(DEFAULT_POST_TEMPLATE, product)
