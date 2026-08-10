from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.amazon.models import (
    ProductSnapshot,
)
from app.deal_engine import (
    DEFAULT_DEAL_RULES,
    DealEvaluation,
    DealRules,
    evaluate_deal,
)


# =========================================================
# CANDIDATO
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class DealCandidate:
    """
    Prodotto già analizzato
    dal Deal Engine.
    """

    product: ProductSnapshot

    evaluation: DealEvaluation


# =========================================================
# RISULTATO BATCH
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class DealBatchResult:
    """
    Risultato dell'analisi
    di una lista di prodotti.
    """

    scanned_count: int

    valid_candidates: tuple[
        DealCandidate,
        ...
    ]

    rejected_candidates: tuple[
        DealCandidate,
        ...
    ]

    @property
    def valid_count(
        self,
    ) -> int:
        return len(
            self.valid_candidates
        )

    @property
    def rejected_count(
        self,
    ) -> int:
        return len(
            self.rejected_candidates
        )


# =========================================================
# SORTING
# =========================================================


def candidate_sort_key(
    candidate: DealCandidate,
) -> tuple[
    int,
    Decimal,
    Decimal,
    int,
]:
    """
    Ordinamento:

    1. score
    2. sconto
    3. risparmio €
    4. recensioni
    """

    evaluation = (
        candidate.evaluation
    )

    product = (
        candidate.product
    )

    discount = (
        evaluation
        .discount_percentage
    )

    savings = (
        evaluation
        .savings_amount
    )

    reviews = (
        product.reviews_count
        or 0
    )

    return (
        evaluation.score,
        (
            discount
            if discount is not None
            else Decimal("-1")
        ),
        (
            savings
            if savings is not None
            else Decimal("-1")
        ),
        reviews,
    )


# =========================================================
# BATCH ENGINE
# =========================================================


def evaluate_products(
    products: Iterable[
        ProductSnapshot
    ],
    rules: DealRules = (
        DEFAULT_DEAL_RULES
    ),
) -> DealBatchResult:
    """
    Analizza una lista qualsiasi
    di ProductSnapshot.

    Questa funzione NON conosce:
    - Telegram
    - Amazon API
    - database
    - scheduler

    Riceve prodotti e restituisce
    quelli validi e quelli scartati.
    """

    product_list = tuple(
        products
    )

    valid: list[
        DealCandidate
    ] = []

    rejected: list[
        DealCandidate
    ] = []

    for product in product_list:
        evaluation = (
            evaluate_deal(
                product,
                rules,
            )
        )

        candidate = (
            DealCandidate(
                product=product,
                evaluation=evaluation,
            )
        )

        if evaluation.is_deal:
            valid.append(
                candidate
            )

        else:
            rejected.append(
                candidate
            )

    #
    # I prodotti migliori vengono
    # messi per primi.
    #
    valid.sort(
        key=candidate_sort_key,
        reverse=True,
    )

    #
    # Anche gli scartati vengono
    # ordinati per score.
    #
    # È utile per capire quali
    # prodotti erano quasi validi.
    #
    rejected.sort(
        key=candidate_sort_key,
        reverse=True,
    )

    return DealBatchResult(
        scanned_count=len(
            product_list
        ),
        valid_candidates=tuple(
            valid
        ),
        rejected_candidates=tuple(
            rejected
        ),
    )


def select_best_deals(
    products: Iterable[
        ProductSnapshot
    ],
    limit: int = 10,
    rules: DealRules = (
        DEFAULT_DEAL_RULES
    ),
) -> tuple[
    DealCandidate,
    ...
]:
    """
    Restituisce direttamente
    i migliori prodotti validi.

    Questa sarà una delle funzioni
    utilizzate dall'Autoposting.
    """

    if limit <= 0:
        return ()

    result = evaluate_products(
        products,
        rules,
    )

    return (
        result.valid_candidates[
            :limit
        ]
    )
