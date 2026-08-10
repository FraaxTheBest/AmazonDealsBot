from dataclasses import dataclass
from typing import Iterable

from app.amazon.models import (
    ProductSnapshot,
)


@dataclass(
    frozen=True,
    slots=True,
)
class CategoryDefinition:
    key: str

    label: str

    emoji: str


AUTOPOST_CATEGORIES = (
    CategoryDefinition(
        key="electronics",
        label="Elettronica",
        emoji="📱",
    ),
    CategoryDefinition(
        key="computers",
        label="Informatica",
        emoji="💻",
    ),
    CategoryDefinition(
        key="home_kitchen",
        label="Casa e cucina",
        emoji="🏠",
    ),
    CategoryDefinition(
        key="garden",
        label="Giardino",
        emoji="🌿",
    ),
    CategoryDefinition(
        key="beauty",
        label="Bellezza",
        emoji="💄",
    ),
    CategoryDefinition(
        key="health",
        label="Salute",
        emoji="❤️",
    ),
    CategoryDefinition(
        key="sports",
        label="Sport",
        emoji="⚽",
    ),
    CategoryDefinition(
        key="toys",
        label="Giochi",
        emoji="🧸",
    ),
    CategoryDefinition(
        key="fashion",
        label="Moda",
        emoji="👕",
    ),
    CategoryDefinition(
        key="automotive",
        label="Auto e moto",
        emoji="🚗",
    ),
    CategoryDefinition(
        key="books",
        label="Libri",
        emoji="📚",
    ),
    CategoryDefinition(
        key="pets",
        label="Animali",
        emoji="🐾",
    ),
    CategoryDefinition(
        key="grocery",
        label="Alimentari",
        emoji="🛒",
    ),
)


CATEGORY_BY_KEY = {
    category.key: category
    for category in AUTOPOST_CATEGORIES
}


def normalize_categories(
    values: Iterable[str],
) -> tuple[str, ...]:
    """
    Mantiene solo categorie
    riconosciute dal bot.
    """

    normalized: list[str] = []

    for value in values:
        key = value.strip()

        if (
            key in CATEGORY_BY_KEY
            and key not in normalized
        ):
            normalized.append(
                key
            )

    return tuple(
        normalized
    )


def category_label(
    key: str,
) -> str:
    category = CATEGORY_BY_KEY.get(
        key
    )

    if category is None:
        return key

    return (
        f"{category.emoji} "
        f"{category.label}"
    )


def categories_summary(
    selected: Iterable[str],
) -> str:
    selected_tuple = (
        normalize_categories(
            selected
        )
    )

    if not selected_tuple:
        return "🌐 Tutte"

    return ", ".join(
        category_label(
            key
        )
        for key in selected_tuple
    )


def product_matches_categories(
    product: ProductSnapshot,
    selected_categories: Iterable[str],
) -> bool:
    """
    Nessuna categoria selezionata
    significa TUTTE.
    """

    selected = normalize_categories(
        selected_categories
    )

    if not selected:
        return True

    if not product.category_key:
        return False

    return (
        product.category_key
        in selected
    )


def filter_products_by_categories(
    products: Iterable[
        ProductSnapshot
    ],
    selected_categories: Iterable[str],
) -> list[
    ProductSnapshot
]:
    return [
        product
        for product in products
        if product_matches_categories(
            product,
            selected_categories,
        )
    ]
