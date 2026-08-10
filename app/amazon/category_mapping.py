"""Mapping interno -> SearchIndex ufficiale Amazon.it."""

INTERNAL_TO_AMAZON_IT_SEARCH_INDEX: dict[str, str] = {
    "electronics": "Electronics",
    "computers": "Computers",
    "home_kitchen": "HomeAndKitchen",
    "garden": "GardenAndOutdoor",
    "beauty": "Beauty",
    "health": "HealthPersonalCare",
    "sports": "SportsAndOutdoors",
    "toys": "ToysAndGames",
    "fashion": "Fashion",
    "automotive": "Automotive",
    "books": "Books",
    "pets": "PetSupplies",
    "grocery": "GroceryAndGourmetFood",
}


def category_to_search_index(category_key: str | None) -> str:
    if not category_key:
        return "All"
    return INTERNAL_TO_AMAZON_IT_SEARCH_INDEX.get(category_key, "All")
