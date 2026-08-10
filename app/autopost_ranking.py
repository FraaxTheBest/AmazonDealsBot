from dataclasses import dataclass
from decimal import Decimal

from app.autopost_advanced_store import (
    ChannelAutopostAdvancedConfig,
    daily_publication_counts,
    effective_max_posts_per_day,
    failed_candidate_asins,
    get_blacklist_sets,
    get_or_create_advanced_config,
    list_recent_decisions,
    normalize_text,
)
from app.autopost_queue_store import (
    AutopostCandidate,
    candidate_product,
)
from app.config import get_settings
from app.deal_pipeline import DealCandidate


OFFER_LIGHTNING = "lightning"
OFFER_COUPON = "coupon"
OFFER_LOWEST = "lowest"
OFFER_WAREHOUSE = "warehouse"
OFFER_NORMAL = "normal"
OFFER_ERROR = "error"


@dataclass(frozen=True, slots=True)
class RankedDealCandidate:
    candidate: DealCandidate
    offer_type: str
    priority_bonus: int
    final_score: int
    source_index: int


@dataclass(frozen=True, slots=True)
class RankedQueueCandidate:
    candidate: AutopostCandidate
    offer_type: str
    priority_bonus: int
    final_score: int
    source_index: int


@dataclass(frozen=True, slots=True)
class AdvancedRankingResult:
    input_count: int
    blacklist_rejected_count: int
    limit_rejected_count: int
    failed_rejected_count: int
    ranked: tuple[RankedDealCandidate, ...]


@dataclass(frozen=True, slots=True)
class QueueRankingResult:
    input_count: int
    blacklist_rejected_count: int
    limit_rejected_count: int
    ranked: tuple[RankedQueueCandidate, ...]


def normalize_offer_type(value: str | None) -> str:
    normalized = normalize_text(value)

    aliases = {
        "lightning": OFFER_LIGHTNING,
        "lightningdeal": OFFER_LIGHTNING,
        "lightning deal": OFFER_LIGHTNING,
        "coupon": OFFER_COUPON,
        "lowest": OFFER_LOWEST,
        "lowest price": OFFER_LOWEST,
        "warehouse": OFFER_WAREHOUSE,
        "normal": OFFER_NORMAL,
        "nodiscount": OFFER_NORMAL,
        "no discount": OFFER_NORMAL,
        "error": OFFER_ERROR,
    }

    return aliases.get(normalized, OFFER_NORMAL)


def product_offer_type(product) -> str:
    return normalize_offer_type(
        getattr(product, "offer_type", None)
    )


def priority_bonus(
    config: ChannelAutopostAdvancedConfig,
    offer_type: str,
) -> int:
    values = {
        OFFER_LIGHTNING: int(config.priority_lightning),
        OFFER_COUPON: int(config.priority_coupon),
        OFFER_LOWEST: int(config.priority_lowest),
        OFFER_WAREHOUSE: int(config.priority_warehouse),
        OFFER_NORMAL: int(config.priority_normal),
    }

    return values.get(offer_type, 0)


def _decimal_or_negative(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("-1")


def _updated_timestamp(product) -> float:
    value = getattr(product, "source_updated_at", None)
    if value is None:
        return 0.0

    try:
        return float(value.timestamp())
    except (ValueError, OSError, AttributeError):
        return 0.0


def _deal_sort_key(
    item: RankedDealCandidate,
    ranking_mode: str,
):
    candidate = item.candidate
    evaluation = candidate.evaluation
    product = candidate.product

    discount = _decimal_or_negative(
        evaluation.discount_percentage
    )
    savings = _decimal_or_negative(
        evaluation.savings_amount
    )
    reviews = product.reviews_count or 0

    if ranking_mode == "discount":
        return (
            item.priority_bonus,
            discount,
            item.final_score,
            savings,
            reviews,
        )

    if ranking_mode == "recent":
        return (
            item.priority_bonus,
            _updated_timestamp(product),
            -item.source_index,
            item.final_score,
        )

    return (
        item.final_score,
        discount,
        savings,
        reviews,
    )


def _queue_sort_key(
    item: RankedQueueCandidate,
    ranking_mode: str,
):
    candidate = item.candidate
    product = candidate_product(candidate)

    discount = _decimal_or_negative(
        candidate.discount_percentage
    )
    savings = _decimal_or_negative(
        candidate.savings_amount
    )

    if ranking_mode == "discount":
        return (
            item.priority_bonus,
            discount,
            item.final_score,
            savings,
        )

    if ranking_mode == "recent":
        return (
            item.priority_bonus,
            _updated_timestamp(product),
            -item.source_index,
            item.final_score,
        )

    return (
        item.final_score,
        discount,
        savings,
    )


def _passes_blacklist(
    product,
    brand_blacklist: frozenset[str],
    seller_blacklist: frozenset[str],
    manufacturer_blacklist: frozenset[str],
    asin_blacklist: frozenset[str],
    keyword_blacklist: frozenset[str],
) -> bool:
    brand = normalize_text(product.brand)
    seller = normalize_text(product.seller)
    manufacturer = normalize_text(getattr(product, "manufacturer", None))
    asin = (product.asin or "").strip().upper()
    title = normalize_text(product.title)

    if brand and brand in brand_blacklist:
        return False
    if seller and seller in seller_blacklist:
        return False
    if manufacturer and manufacturer in manufacturer_blacklist:
        return False
    if asin and asin in asin_blacklist:
        return False
    if title and any(keyword in title for keyword in keyword_blacklist if keyword):
        return False
    return True


def _passes_daily_limits(
    product,
    config: ChannelAutopostAdvancedConfig,
    total_today: int,
    by_brand: dict[str, int],
    by_category: dict[str, int],
    max_posts_override: int | None,
) -> bool:
    max_posts = (
        int(max_posts_override)
        if max_posts_override is not None
        else int(config.max_posts_per_day)
    )

    if max_posts > 0 and total_today >= max_posts:
        return False

    brand = normalize_text(product.brand)
    category = normalize_text(product.category_key)

    if (
        int(config.max_brand_per_day) > 0
        and brand
        and by_brand.get(brand, 0) >= int(config.max_brand_per_day)
    ):
        return False

    if (
        int(config.max_category_per_day) > 0
        and category
        and by_category.get(category, 0)
        >= int(config.max_category_per_day)
    ):
        return False

    return True


def _rotate_deals(
    items: list[RankedDealCandidate],
    config: ChannelAutopostAdvancedConfig,
    previous_brand: str,
    previous_category: str,
) -> list[RankedDealCandidate]:
    remaining = list(items)
    result: list[RankedDealCandidate] = []
    last_brand = previous_brand
    last_category = previous_category

    while remaining:
        chosen_index = 0

        for index, item in enumerate(remaining):
            product = item.candidate.product
            brand = normalize_text(product.brand)
            category = normalize_text(product.category_key)

            brand_ok = (
                not config.alternate_brands
                or not last_brand
                or not brand
                or brand != last_brand
            )
            category_ok = (
                not config.alternate_categories
                or not last_category
                or not category
                or category != last_category
            )

            if brand_ok and category_ok:
                chosen_index = index
                break

        chosen = remaining.pop(chosen_index)
        result.append(chosen)

        chosen_product = chosen.candidate.product
        chosen_brand = normalize_text(chosen_product.brand)
        chosen_category = normalize_text(chosen_product.category_key)

        if chosen_brand:
            last_brand = chosen_brand
        if chosen_category:
            last_category = chosen_category

    return result


def _rotate_queue(
    items: list[RankedQueueCandidate],
    config: ChannelAutopostAdvancedConfig,
    previous_brand: str,
    previous_category: str,
) -> list[RankedQueueCandidate]:
    remaining = list(items)
    result: list[RankedQueueCandidate] = []
    last_brand = previous_brand
    last_category = previous_category

    while remaining:
        chosen_index = 0

        for index, item in enumerate(remaining):
            product = candidate_product(item.candidate)
            brand = normalize_text(product.brand)
            category = normalize_text(product.category_key)

            brand_ok = (
                not config.alternate_brands
                or not last_brand
                or not brand
                or brand != last_brand
            )
            category_ok = (
                not config.alternate_categories
                or not last_category
                or not category
                or category != last_category
            )

            if brand_ok and category_ok:
                chosen_index = index
                break

        chosen = remaining.pop(chosen_index)
        result.append(chosen)

        product = candidate_product(chosen.candidate)
        brand = normalize_text(product.brand)
        category = normalize_text(product.category_key)
        if brand:
            last_brand = brand
        if category:
            last_category = category

    return result


async def rank_deal_candidates(
    owner_telegram_user_id: int,
    channel_id: int,
    candidates,
    max_posts_override: int | None = None,
) -> AdvancedRankingResult:
    candidate_list = list(candidates)
    settings = get_settings()
    config = await get_or_create_advanced_config(
        owner_telegram_user_id,
        channel_id,
    )
    blacklist = await get_blacklist_sets(
        owner_telegram_user_id,
        channel_id,
    )
    counts = await daily_publication_counts(
        owner_telegram_user_id,
        channel_id,
        settings.app_timezone,
    )
    recent = await list_recent_decisions(
        owner_telegram_user_id,
        channel_id,
        limit=1,
    )
    failed_asins = await failed_candidate_asins(
        owner_telegram_user_id,
        channel_id,
    )

    previous_brand = normalize_text(recent[0].brand) if recent else ""
    previous_category = (
        normalize_text(recent[0].category_key) if recent else ""
    )

    ranked: list[RankedDealCandidate] = []
    blacklist_rejected = 0
    limit_rejected = 0
    failed_rejected = 0

    effective_max = (
        max_posts_override
        if max_posts_override is not None
        else effective_max_posts_per_day(config)
    )

    for index, candidate in enumerate(candidate_list):
        product = candidate.product
        asin = product.asin.strip().upper()

        if asin in failed_asins:
            failed_rejected += 1
            continue

        offer_type = product_offer_type(product)
        if offer_type == OFFER_ERROR:
            blacklist_rejected += 1
            continue

        if not _passes_blacklist(
            product,
            blacklist.brands,
            blacklist.sellers,
            blacklist.manufacturers,
            blacklist.asins,
            blacklist.keywords,
        ):
            blacklist_rejected += 1
            continue

        if not _passes_daily_limits(
            product,
            config,
            counts.total,
            counts.by_brand,
            counts.by_category,
            effective_max,
        ):
            limit_rejected += 1
            continue

        bonus = priority_bonus(config, offer_type)
        ranked.append(
            RankedDealCandidate(
                candidate=candidate,
                offer_type=offer_type,
                priority_bonus=bonus,
                final_score=candidate.evaluation.score + bonus,
                source_index=index,
            )
        )

    ranked.sort(
        key=lambda item: _deal_sort_key(item, config.ranking_mode),
        reverse=True,
    )

    ranked = _rotate_deals(
        ranked,
        config,
        previous_brand,
        previous_category,
    )

    return AdvancedRankingResult(
        input_count=len(candidate_list),
        blacklist_rejected_count=blacklist_rejected,
        limit_rejected_count=limit_rejected,
        failed_rejected_count=failed_rejected,
        ranked=tuple(ranked),
    )


async def rank_queue_candidates(
    owner_telegram_user_id: int,
    channel_id: int,
    candidates: list[AutopostCandidate],
    max_posts_override: int | None = None,
) -> QueueRankingResult:
    settings = get_settings()
    config = await get_or_create_advanced_config(
        owner_telegram_user_id,
        channel_id,
    )
    blacklist = await get_blacklist_sets(
        owner_telegram_user_id,
        channel_id,
    )
    counts = await daily_publication_counts(
        owner_telegram_user_id,
        channel_id,
        settings.app_timezone,
    )
    recent = await list_recent_decisions(
        owner_telegram_user_id,
        channel_id,
        limit=1,
    )

    previous_brand = normalize_text(recent[0].brand) if recent else ""
    previous_category = (
        normalize_text(recent[0].category_key) if recent else ""
    )

    ranked: list[RankedQueueCandidate] = []
    blacklist_rejected = 0
    limit_rejected = 0

    effective_max = (
        max_posts_override
        if max_posts_override is not None
        else effective_max_posts_per_day(config)
    )

    for index, candidate in enumerate(candidates):
        product = candidate_product(candidate)
        offer_type = product_offer_type(product)

        if offer_type == OFFER_ERROR:
            blacklist_rejected += 1
            continue

        if not _passes_blacklist(
            product,
            blacklist.brands,
            blacklist.sellers,
            blacklist.manufacturers,
            blacklist.asins,
            blacklist.keywords,
        ):
            blacklist_rejected += 1
            continue

        if not _passes_daily_limits(
            product,
            config,
            counts.total,
            counts.by_brand,
            counts.by_category,
            effective_max,
        ):
            limit_rejected += 1
            continue

        bonus = priority_bonus(config, offer_type)
        ranked.append(
            RankedQueueCandidate(
                candidate=candidate,
                offer_type=offer_type,
                priority_bonus=bonus,
                final_score=candidate.score + bonus,
                source_index=index,
            )
        )

    ranked.sort(
        key=lambda item: _queue_sort_key(item, config.ranking_mode),
        reverse=True,
    )

    ranked = _rotate_queue(
        ranked,
        config,
        previous_brand,
        previous_category,
    )

    return QueueRankingResult(
        input_count=len(candidates),
        blacklist_rejected_count=blacklist_rejected,
        limit_rejected_count=limit_rejected,
        ranked=tuple(ranked),
    )
