from dataclasses import dataclass
from decimal import (
    Decimal,
    ROUND_HALF_UP,
)

from app.amazon.models import (
    ProductSnapshot,
)


# =========================================================
# CONFIGURAZIONE BASE
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class DealRules:
    """
    Regole globali iniziali.

    Nella Fase 9 queste regole
    diventeranno configurabili
    per ogni canale.
    """

    min_discount_percentage: Decimal = (
        Decimal("10")
    )

    min_score: int = 60


DEFAULT_DEAL_RULES = DealRules()


# =========================================================
# RISULTATO DEAL ENGINE
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class DealEvaluation:
    is_deal: bool

    score: int

    verdict: str

    discount_percentage: (
        Decimal | None
    )

    savings_amount: (
        Decimal | None
    )

    reasons: tuple[str, ...]

    blockers: tuple[str, ...]


# =========================================================
# HELPERS
# =========================================================


def normalize_percentage(
    value: Decimal,
) -> Decimal:
    return value.quantize(
        Decimal("0.1"),
        rounding=ROUND_HALF_UP,
    )


def calculate_discount_percentage(
    product: ProductSnapshot,
) -> Decimal | None:
    """
    Se abbiamo entrambi i prezzi,
    calcoliamo lo sconto direttamente.

    Altrimenti utilizziamo il dato
    fornito dal provider.
    """

    current_price = (
        product.current_price
    )

    original_price = (
        product.original_price
    )

    if (
        current_price is not None
        and original_price is not None
        and original_price > 0
    ):
        if current_price >= original_price:
            return Decimal("0")

        discount = (
            (
                original_price
                - current_price
            )
            / original_price
            * Decimal("100")
        )

        return normalize_percentage(
            discount
        )

    if (
        product.discount_percentage
        is not None
    ):
        if (
            product.discount_percentage
            < 0
        ):
            return Decimal("0")

        return normalize_percentage(
            product.discount_percentage
        )

    return None


def calculate_savings(
    product: ProductSnapshot,
) -> Decimal | None:
    if (
        product.current_price is None
        or product.original_price is None
    ):
        return None

    savings = (
        product.original_price
        - product.current_price
    )

    if savings <= 0:
        return None

    return savings.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def is_unavailable(
    product: ProductSnapshot,
) -> bool:
    if not product.availability:
        return False

    availability = (
        product.availability
        .strip()
        .lower()
    )

    unavailable_markers = (
        "non disponibile",
        "temporaneamente non disponibile",
        "esaurito",
        "unavailable",
        "out of stock",
    )

    return any(
        marker in availability
        for marker in unavailable_markers
    )


def is_amazon_value(
    value: str | None,
) -> bool:
    if not value:
        return False

    normalized = (
        value.strip().lower()
    )

    return (
        normalized == "amazon"
        or normalized.startswith(
            "amazon."
        )
    )


# =========================================================
# SCORE
# =========================================================


def discount_score(
    discount: Decimal | None,
) -> int:
    if discount is None:
        return 0

    if discount >= 40:
        return 50

    if discount >= 30:
        return 45

    if discount >= 20:
        return 35

    if discount >= 15:
        return 25

    if discount >= 10:
        return 15

    return 0


def savings_score(
    savings: Decimal | None,
) -> int:
    if savings is None:
        return 0

    if savings >= 50:
        return 10

    if savings >= 20:
        return 8

    if savings >= 10:
        return 6

    if savings >= 5:
        return 3

    if savings > 0:
        return 1

    return 0


def rating_score(
    rating: Decimal | None,
) -> int:
    if rating is None:
        return 0

    if rating >= Decimal("4.7"):
        return 15

    if rating >= Decimal("4.5"):
        return 13

    if rating >= Decimal("4.2"):
        return 10

    if rating >= Decimal("4.0"):
        return 7

    if rating >= Decimal("3.5"):
        return 3

    return 0


def reviews_score(
    reviews: int | None,
) -> int:
    if reviews is None:
        return 0

    if reviews >= 1000:
        return 10

    if reviews >= 500:
        return 8

    if reviews >= 100:
        return 6

    if reviews >= 50:
        return 4

    if reviews >= 10:
        return 2

    return 0


def availability_score(
    product: ProductSnapshot,
) -> int:
    if not product.availability:
        return 0

    if is_unavailable(
        product
    ):
        return 0

    return 10


def fulfillment_score(
    product: ProductSnapshot,
) -> int:
    sold_by_amazon = (
        is_amazon_value(
            product.seller
        )
    )

    shipped_by_amazon = (
        is_amazon_value(
            product.ships_from
        )
    )

    if (
        sold_by_amazon
        and shipped_by_amazon
    ):
        return 5

    if shipped_by_amazon:
        return 3

    return 0


# =========================================================
# DEAL ENGINE
# =========================================================


def evaluate_deal(
    product: ProductSnapshot,
    rules: DealRules = (
        DEFAULT_DEAL_RULES
    ),
) -> DealEvaluation:
    """
    Analizza un prodotto e restituisce
    un giudizio indipendente dal bot
    Telegram.

    Questo permetterà in futuro di
    utilizzare lo stesso Deal Engine
    sia nei post manuali sia
    nell'Autoposting.
    """

    reasons: list[str] = []

    blockers: list[str] = []

    discount = (
        calculate_discount_percentage(
            product
        )
    )

    savings = calculate_savings(
        product
    )

    # -----------------------------------------------------
    # CONTROLLI OBBLIGATORI
    # -----------------------------------------------------

    if product.current_price is None:
        blockers.append(
            "Prezzo attuale mancante."
        )

    elif product.current_price <= 0:
        blockers.append(
            "Prezzo attuale non valido."
        )

    if is_unavailable(
        product
    ):
        blockers.append(
            "Prodotto non disponibile."
        )

    if discount is None:
        blockers.append(
            "Sconto non disponibile."
        )

    elif (
        discount
        < rules.min_discount_percentage
    ):
        blockers.append(
            (
                f"Sconto {discount}% "
                f"inferiore al minimo "
                f"{rules.min_discount_percentage}%."
            )
        )

    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    score_discount = discount_score(
        discount
    )

    score_savings = savings_score(
        savings
    )

    score_rating = rating_score(
        product.rating
    )

    score_reviews = reviews_score(
        product.reviews_count
    )

    score_availability = (
        availability_score(
            product
        )
    )

    score_fulfillment = (
        fulfillment_score(
            product
        )
    )

    score = (
        score_discount
        + score_savings
        + score_rating
        + score_reviews
        + score_availability
        + score_fulfillment
    )

    # Protezione futura:
    # lo score non supera mai 100.
    score = min(
        max(score, 0),
        100,
    )

    # -----------------------------------------------------
    # MOTIVAZIONI
    # -----------------------------------------------------

    if discount is not None:
        reasons.append(
            f"Sconto: {discount}% "
            f"(+{score_discount} punti)"
        )

    if savings is not None:
        reasons.append(
            (
                f"Risparmio: "
                f"{savings:.2f}€ "
                f"(+{score_savings} punti)"
            )
        )

    if product.rating is not None:
        reasons.append(
            (
                f"Rating: "
                f"{product.rating}/5 "
                f"(+{score_rating} punti)"
            )
        )

    if product.reviews_count is not None:
        reasons.append(
            (
                f"Recensioni: "
                f"{product.reviews_count} "
                f"(+{score_reviews} punti)"
            )
        )

    if product.availability:
        reasons.append(
            (
                "Disponibilità "
                f"(+{score_availability} punti)"
            )
        )

    if score_fulfillment:
        reasons.append(
            (
                "Gestione Amazon "
                f"(+{score_fulfillment} punti)"
            )
        )

    # -----------------------------------------------------
    # VERDETTO
    # -----------------------------------------------------

    has_blockers = bool(
        blockers
    )

    is_deal = (
        not has_blockers
        and score >= rules.min_score
    )

    if has_blockers:
        verdict = "SCARTATA"

    elif score >= 80:
        verdict = "ECCELLENTE"

    elif score >= 60:
        verdict = "BUONA"

    elif score >= 40:
        verdict = "DEBOLE"

    else:
        verdict = "NON INTERESSANTE"

    if (
        not has_blockers
        and score < rules.min_score
    ):
        reasons.append(
            (
                f"Punteggio sotto la "
                f"soglia minima "
                f"({rules.min_score})."
            )
        )

    return DealEvaluation(
        is_deal=is_deal,
        score=score,
        verdict=verdict,
        discount_percentage=discount,
        savings_amount=savings,
        reasons=tuple(
            reasons
        ),
        blockers=tuple(
            blockers
        ),
    )


# =========================================================
# TESTO ADMIN
# =========================================================


def deal_admin_text(
    evaluation: DealEvaluation,
) -> str:
    if evaluation.is_deal:
        status = (
            "✅ VALIDA PER AUTOPOST"
        )

    else:
        status = (
            "❌ NON VALIDA PER AUTOPOST"
        )

    lines = [
        "🧠 <b>Deal Engine</b>",
        "",
        status,
        (
            f"🎯 Score: "
            f"<b>{evaluation.score}/100</b>"
        ),
        (
            f"🏷 Giudizio: "
            f"<b>{evaluation.verdict}</b>"
        ),
    ]

    if (
        evaluation.discount_percentage
        is not None
    ):
        lines.append(
            (
                f"📉 Sconto: "
                f"<b>"
                f"{evaluation.discount_percentage}%"
                f"</b>"
            )
        )

    if (
        evaluation.savings_amount
        is not None
    ):
        savings_text = (
            f"{evaluation.savings_amount:.2f}"
            .replace(".", ",")
        )

        lines.append(
            (
                f"💶 Risparmio: "
                f"<b>{savings_text}€</b>"
            )
        )

    if evaluation.blockers:
        lines.append(
            ""
        )

        lines.append(
            "🚫 <b>Motivi scarto:</b>"
        )

        for blocker in (
            evaluation.blockers
        ):
            lines.append(
                f"• {blocker}"
            )

    return "\n".join(
        lines
    )


# =========================================================
# DIAGNOSTICA LOCALE
# =========================================================


def print_test(
    name: str,
    product: ProductSnapshot,
) -> None:
    evaluation = evaluate_deal(
        product
    )

    print()
    print("=" * 60)
    print(name)
    print("=" * 60)

    print(
        f"ASIN: {product.asin}"
    )

    print(
        f"Score: "
        f"{evaluation.score}/100"
    )

    print(
        f"Verdetto: "
        f"{evaluation.verdict}"
    )

    print(
        f"Autopost: "
        f"{evaluation.is_deal}"
    )

    print(
        f"Sconto: "
        f"{evaluation.discount_percentage}"
    )

    print(
        f"Risparmio: "
        f"{evaluation.savings_amount}"
    )

    if evaluation.blockers:
        print(
            "Blocchi:"
        )

        for blocker in (
            evaluation.blockers
        ):
            print(
                f" - {blocker}"
            )


def main() -> None:
    """
    Test locale della Fase 8A.

    Non usa Telegram.
    Non usa Amazon.
    Non modifica il database.
    """

    strong_deal = ProductSnapshot(
        asin="B0TEST0001",
        title="Prodotto test ottimo",
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0TEST0001"
        ),
        current_price=Decimal(
            "79.99"
        ),
        original_price=Decimal(
            "99.99"
        ),
        rating=Decimal(
            "4.7"
        ),
        reviews_count=66,
        availability="Disponibile",
        seller="Negozio Demo",
        ships_from="Amazon",
    )

    weak_deal = ProductSnapshot(
        asin="B0TEST0002",
        title="Prodotto test debole",
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0TEST0002"
        ),
        current_price=Decimal(
            "94.99"
        ),
        original_price=Decimal(
            "99.99"
        ),
        rating=Decimal(
            "3.8"
        ),
        reviews_count=5,
        availability="Disponibile",
        seller="Negozio Demo",
        ships_from="Negozio Demo",
    )

    unavailable_deal = (
        ProductSnapshot(
            asin="B0TEST0003",
            title=(
                "Prodotto non disponibile"
            ),
            detail_url=(
                "https://www.amazon.it/"
                "dp/B0TEST0003"
            ),
            current_price=Decimal(
                "49.99"
            ),
            original_price=Decimal(
                "99.99"
            ),
            rating=Decimal(
                "4.9"
            ),
            reviews_count=1500,
            availability=(
                "Non disponibile"
            ),
            seller="Amazon",
            ships_from="Amazon",
        )
    )

    print_test(
        "TEST 1 - OFFERTA BUONA",
        strong_deal,
    )

    print_test(
        "TEST 2 - SCONTO TROPPO BASSO",
        weak_deal,
    )

    print_test(
        "TEST 3 - NON DISPONIBILE",
        unavailable_deal,
    )


if __name__ == "__main__":
    main()
