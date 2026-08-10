from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.amazon.models import (
    ProductSnapshot,
)
from app.deal_engine import (
    DealRules,
    is_amazon_value,
)
from app.deal_pipeline import (
    DealBatchResult,
    evaluate_products,
)


@dataclass(
    frozen=True,
    slots=True,
)
class AutopostFilterRules:
    min_discount_percentage: Decimal = (
        Decimal("10")
    )

    min_score: int = 60

    min_rating: Decimal | None = None

    min_reviews: int | None = None

    min_price: Decimal | None = None

    max_price: Decimal | None = None

    require_amazon_shipping: bool = False


@dataclass(
    frozen=True,
    slots=True,
)
class FilterRejectedProduct:
    product: ProductSnapshot

    reasons: tuple[str, ...]


@dataclass(
    frozen=True,
    slots=True,
)
class ChannelPipelineResult:
    total_count: int

    filter_passed_products: tuple[
        ProductSnapshot,
        ...
    ]

    rejected_by_filters: tuple[
        FilterRejectedProduct,
        ...
    ]

    deal_result: DealBatchResult

    @property
    def filter_passed_count(
        self,
    ) -> int:
        return len(
            self.filter_passed_products
        )

    @property
    def filter_rejected_count(
        self,
    ) -> int:
        return len(
            self.rejected_by_filters
        )


def evaluate_static_filters(
    product: ProductSnapshot,
    rules: AutopostFilterRules,
) -> tuple[
    bool,
    tuple[str, ...],
]:
    """
    Filtri esterni al Deal Engine.

    Sconto minimo e score minimo
    vengono invece passati direttamente
    al Deal Engine.
    """

    reasons: list[str] = []

    # =====================================================
    # PREZZO
    # =====================================================

    if (
        rules.min_price is not None
        or rules.max_price is not None
    ):
        if product.current_price is None:
            reasons.append(
                "Prezzo attuale mancante."
            )

        else:
            if (
                rules.min_price is not None
                and product.current_price
                < rules.min_price
            ):
                reasons.append(
                    (
                        f"Prezzo "
                        f"{product.current_price}€ "
                        f"inferiore al minimo "
                        f"{rules.min_price}€."
                    )
                )

            if (
                rules.max_price is not None
                and product.current_price
                > rules.max_price
            ):
                reasons.append(
                    (
                        f"Prezzo "
                        f"{product.current_price}€ "
                        f"superiore al massimo "
                        f"{rules.max_price}€."
                    )
                )

    # =====================================================
    # RATING
    # =====================================================

    if rules.min_rating is not None:
        if product.rating is None:
            reasons.append(
                "Rating mancante."
            )

        elif (
            product.rating
            < rules.min_rating
        ):
            reasons.append(
                (
                    f"Rating "
                    f"{product.rating}/5 "
                    f"inferiore al minimo "
                    f"{rules.min_rating}/5."
                )
            )

    # =====================================================
    # RECENSIONI
    # =====================================================

    if rules.min_reviews is not None:
        if product.reviews_count is None:
            reasons.append(
                "Numero recensioni mancante."
            )

        elif (
            product.reviews_count
            < rules.min_reviews
        ):
            reasons.append(
                (
                    f"Recensioni "
                    f"{product.reviews_count} "
                    f"inferiori al minimo "
                    f"{rules.min_reviews}."
                )
            )

    # =====================================================
    # SPEDIZIONE AMAZON
    # =====================================================

    if rules.require_amazon_shipping:
        if not is_amazon_value(
            product.ships_from
        ):
            reasons.append(
                "Prodotto non spedito da Amazon."
            )

    return (
        len(reasons) == 0,
        tuple(reasons),
    )


def filter_and_evaluate_products(
    products: Iterable[
        ProductSnapshot
    ],
    rules: AutopostFilterRules,
) -> ChannelPipelineResult:
    """
    Pipeline:

    filtri extra
        ↓
    Deal Engine
        ↓
    ranking
    """

    product_list = tuple(
        products
    )

    passed: list[
        ProductSnapshot
    ] = []

    rejected: list[
        FilterRejectedProduct
    ] = []

    for product in product_list:
        is_valid, reasons = (
            evaluate_static_filters(
                product,
                rules,
            )
        )

        if is_valid:
            passed.append(
                product
            )

        else:
            rejected.append(
                FilterRejectedProduct(
                    product=product,
                    reasons=reasons,
                )
            )

    deal_rules = DealRules(
        min_discount_percentage=(
            rules.min_discount_percentage
        ),
        min_score=rules.min_score,
    )

    deal_result = evaluate_products(
        passed,
        deal_rules,
    )

    return ChannelPipelineResult(
        total_count=len(
            product_list
        ),
        filter_passed_products=tuple(
            passed
        ),
        rejected_by_filters=tuple(
            rejected
        ),
        deal_result=deal_result,
    )
