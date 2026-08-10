from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.amazon.models import ProductSnapshot
from app.autopost_filters import (
    AutopostFilterRules,
    ChannelPipelineResult,
    filter_and_evaluate_products,
)
from app.autopost_store import (
    ChannelAutopostConfig,
    get_or_create_autopost_config,
    get_selected_categories,
)
from app.categories import (
    filter_products_by_categories,
)
from app.deal_pipeline import DealCandidate
from app.dedupe_store import (
    DedupeResult,
    filter_recent_duplicates,
)


# =========================================================
# RISULTATO PIPELINE COMPLETA
# =========================================================


@dataclass(
    frozen=True,
    slots=True,
)
class FullAutopostPipelineResult:
    """
    Risultato completo della pipeline
    di selezione Autoposting.

    Ordine:

    provider
        ↓
    categorie
        ↓
    filtri
        ↓
    Deal Engine
        ↓
    anti-duplicati
        ↓
    ranking finale
    """

    source_count: int

    selected_categories: tuple[
        str,
        ...
    ]

    category_passed_products: tuple[
        ProductSnapshot,
        ...
    ]

    filter_result: ChannelPipelineResult

    dedupe_result: DedupeResult

    final_candidates: tuple[
        DealCandidate,
        ...
    ]

    dedupe_window_hours: int

    @property
    def category_passed_count(
        self,
    ) -> int:
        return len(
            self.category_passed_products
        )

    @property
    def category_rejected_count(
        self,
    ) -> int:
        return (
            self.source_count
            - self.category_passed_count
        )

    @property
    def filter_passed_count(
        self,
    ) -> int:
        return (
            self.filter_result
            .filter_passed_count
        )

    @property
    def filter_rejected_count(
        self,
    ) -> int:
        return (
            self.filter_result
            .filter_rejected_count
        )

    @property
    def deal_valid_count(
        self,
    ) -> int:
        return (
            self.filter_result
            .deal_result
            .valid_count
        )

    @property
    def deal_rejected_count(
        self,
    ) -> int:
        return (
            self.filter_result
            .deal_result
            .rejected_count
        )

    @property
    def duplicate_count(
        self,
    ) -> int:
        return (
            self.dedupe_result
            .duplicate_count
        )

    @property
    def final_count(
        self,
    ) -> int:
        return len(
            self.final_candidates
        )


# =========================================================
# CONFIG → FILTER RULES
# =========================================================


def config_to_filter_rules(
    config: ChannelAutopostConfig,
) -> AutopostFilterRules:
    """
    Converte la configurazione DB
    nelle regole usate dal motore.
    """

    return AutopostFilterRules(
        min_discount_percentage=Decimal(
            str(
                config
                .min_discount_percentage
            )
        ),
        min_score=int(
            config.min_score
        ),
        min_rating=(
            Decimal(
                str(config.min_rating)
            )
            if config.min_rating
            is not None
            else None
        ),
        min_reviews=(
            int(config.min_reviews)
            if config.min_reviews
            is not None
            else None
        ),
        min_price=(
            Decimal(
                str(config.min_price)
            )
            if config.min_price
            is not None
            else None
        ),
        max_price=(
            Decimal(
                str(config.max_price)
            )
            if config.max_price
            is not None
            else None
        ),
        require_amazon_shipping=bool(
            config
            .require_amazon_shipping
        ),
    )


# =========================================================
# PIPELINE COMPLETA
# =========================================================


async def run_channel_autopost_pipeline(
    owner_telegram_user_id: int,
    channel_id: int,
    products: Iterable[
        ProductSnapshot
    ],
) -> FullAutopostPipelineResult:
    """
    Esegue tutta la selezione
    Autoposting per uno specifico
    canale.

    Questa funzione NON pubblica.

    Restituisce solamente i
    candidati finali.
    """

    source_products = tuple(
        products
    )

    # =====================================================
    # CONFIG CANALE
    # =====================================================

    config = (
        await get_or_create_autopost_config(
            owner_telegram_user_id,
            channel_id,
        )
    )

    selected_categories = (
        get_selected_categories(
            config
        )
    )

    # =====================================================
    # 1. CATEGORIE
    # =====================================================

    category_products = tuple(
        filter_products_by_categories(
            source_products,
            selected_categories,
        )
    )

    # =====================================================
    # 2. FILTRI + DEAL ENGINE + RANKING
    # =====================================================

    filter_rules = (
        config_to_filter_rules(
            config
        )
    )

    filter_result = (
        filter_and_evaluate_products(
            category_products,
            filter_rules,
        )
    )

    #
    # valid_candidates è già
    # ordinato dal migliore
    # al peggiore dal Deal Engine.
    #
    deal_candidates = (
        filter_result
        .deal_result
        .valid_candidates
    )

    valid_products = tuple(
        candidate.product
        for candidate in deal_candidates
    )

    # =====================================================
    # 3. ANTI-DUPLICATI
    # =====================================================

    dedupe_result = (
        await filter_recent_duplicates(
            owner_telegram_user_id=(
                owner_telegram_user_id
            ),
            channel_id=channel_id,
            products=valid_products,
            window_hours=int(
                config
                .dedupe_window_hours
            ),
        )
    )

    passed_asins = {
        product.asin
        .strip()
        .upper()
        for product
        in dedupe_result
        .passed_products
    }

    # =====================================================
    # 4. CANDIDATI FINALI
    # =====================================================

    #
    # Manteniamo l'ordine originale
    # del Deal Engine.
    #
    # Quindi il prodotto con score
    # migliore resta sempre primo.
    #
    final_candidates = tuple(
        candidate
        for candidate
        in deal_candidates
        if (
            candidate.product.asin
            .strip()
            .upper()
            in passed_asins
        )
    )

    return FullAutopostPipelineResult(
        source_count=len(
            source_products
        ),
        selected_categories=(
            selected_categories
        ),
        category_passed_products=(
            category_products
        ),
        filter_result=(
            filter_result
        ),
        dedupe_result=(
            dedupe_result
        ),
        final_candidates=(
            final_candidates
        ),
        dedupe_window_hours=int(
            config
            .dedupe_window_hours
        ),
    )
