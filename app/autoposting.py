from decimal import (
    Decimal,
    InvalidOperation,
)
from html import escape

from aiogram import (
    F,
    Router,
)
from aiogram.fsm.context import (
    FSMContext,
)
from aiogram.fsm.state import (
    State,
    StatesGroup,
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.amazon.models import (
    ProductSnapshot,
)
from app.autopost_filters import (
    AutopostFilterRules,
    ChannelPipelineResult,
    filter_and_evaluate_products,
)
from app.autopost_store import (
    ChannelAutopostConfig,
    get_or_create_autopost_config,
    get_selected_categories,
    reset_autopost_filters,
    set_autopost_filter,
    set_selected_categories,
)
from app.categories import (
    AUTOPOST_CATEGORIES,
    categories_summary,
    filter_products_by_categories,
)
from app.config import get_settings
from app.database import (
    get_channel,
    list_channels,
)
from app.deal_pipeline import (
    DealBatchResult,
    evaluate_products,
)


router = Router(
    name="autoposting"
)


class AutopostFilterStates(
    StatesGroup
):
    waiting_value = State()


# =========================================================
# DEMO PRODUCTS
# =========================================================


def build_demo_products(
) -> list[
    ProductSnapshot
]:
    excellent = ProductSnapshot(
        asin="B0DEMO0001",
        title=(
            "DEMO - Smartphone "
            "offerta eccellente"
        ),
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0DEMO0001"
        ),
        category_key="electronics",
        current_price=Decimal(
            "69.99"
        ),
        original_price=Decimal(
            "99.99"
        ),
        discount_percentage=Decimal(
            "30"
        ),
        rating=Decimal(
            "4.8"
        ),
        reviews_count=1200,
        availability="Disponibile",
        seller="Amazon",
        ships_from="Amazon",
    )

    good = ProductSnapshot(
        asin="B0DEMO0002",
        title=(
            "DEMO - Casa e cucina "
            "offerta buona"
        ),
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0DEMO0002"
        ),
        category_key="home_kitchen",
        current_price=Decimal(
            "79.99"
        ),
        original_price=Decimal(
            "99.99"
        ),
        discount_percentage=Decimal(
            "20"
        ),
        rating=Decimal(
            "4.7"
        ),
        reviews_count=66,
        availability="Disponibile",
        seller="Negozio Demo",
        ships_from="Amazon",
    )

    weak_discount = ProductSnapshot(
        asin="B0DEMO0003",
        title=(
            "DEMO - Elettronica "
            "sconto basso"
        ),
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0DEMO0003"
        ),
        category_key="electronics",
        current_price=Decimal(
            "94.99"
        ),
        original_price=Decimal(
            "99.99"
        ),
        discount_percentage=Decimal(
            "5"
        ),
        rating=Decimal(
            "4.8"
        ),
        reviews_count=800,
        availability="Disponibile",
        seller="Amazon",
        ships_from="Amazon",
    )

    unavailable = ProductSnapshot(
        asin="B0DEMO0004",
        title=(
            "DEMO - Sport "
            "non disponibile"
        ),
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0DEMO0004"
        ),
        category_key="sports",
        current_price=Decimal(
            "49.99"
        ),
        original_price=Decimal(
            "99.99"
        ),
        discount_percentage=Decimal(
            "50"
        ),
        rating=Decimal(
            "4.9"
        ),
        reviews_count=3000,
        availability=(
            "Non disponibile"
        ),
        seller="Amazon",
        ships_from="Amazon",
    )

    missing_price = ProductSnapshot(
        asin="B0DEMO0005",
        title=(
            "DEMO - Casa "
            "prezzo mancante"
        ),
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0DEMO0005"
        ),
        category_key="home_kitchen",
        current_price=None,
        original_price=Decimal(
            "99.99"
        ),
        discount_percentage=None,
        rating=Decimal(
            "4.6"
        ),
        reviews_count=350,
        availability="Disponibile",
        seller="Amazon",
        ships_from="Amazon",
    )

    return [
        excellent,
        good,
        weak_discount,
        unavailable,
        missing_price,
    ]


# =========================================================
# HELPERS
# =========================================================


def decimal_text(
    value: Decimal | None,
) -> str:
    if value is None:
        return "DISATTIVATO"

    text = format(
        value,
        "f",
    )

    text = text.rstrip(
        "0"
    ).rstrip(
        "."
    )

    return (
        text.replace(
            ".",
            ",",
        )
    )


def config_to_rules(
    config: ChannelAutopostConfig,
) -> AutopostFilterRules:
    return AutopostFilterRules(
        min_discount_percentage=(
            Decimal(
                str(
                    config
                    .min_discount_percentage
                )
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
        require_amazon_shipping=(
            bool(
                config
                .require_amazon_shipping
            )
        ),
    )


def filters_summary(
    config: ChannelAutopostConfig,
) -> str:
    shipping = (
        "✅ SOLO AMAZON"
        if config
        .require_amazon_shipping
        else "❌ DISATTIVATO"
    )

    return (
        f"📉 Sconto minimo: "
        f"<b>"
        f"{decimal_text(
            Decimal(
                str(
                    config
                    .min_discount_percentage
                )
            )
        )}%"
        f"</b>\n"
        f"🎯 Score minimo: "
        f"<b>{config.min_score}/100</b>"
        "\n"
        f"⭐ Rating minimo: "
        f"<b>"
        f"{decimal_text(
            Decimal(
                str(config.min_rating)
            )
            if config.min_rating
            is not None
            else None
        )}"
        f"</b>\n"
        f"💬 Recensioni minime: "
        f"<b>"
        f"{config.min_reviews
        if config.min_reviews
        is not None
        else 'DISATTIVATO'}"
        f"</b>\n"
        f"💶 Prezzo minimo: "
        f"<b>"
        f"{decimal_text(
            Decimal(
                str(config.min_price)
            )
            if config.min_price
            is not None
            else None
        )}"
        f"{'€'
        if config.min_price
        is not None
        else ''}"
        f"</b>\n"
        f"💰 Prezzo massimo: "
        f"<b>"
        f"{decimal_text(
            Decimal(
                str(config.max_price)
            )
            if config.max_price
            is not None
            else None
        )}"
        f"{'€'
        if config.max_price
        is not None
        else ''}"
        f"</b>\n"
        f"📦 Spedizione Amazon: "
        f"<b>{shipping}</b>"
    )


async def get_config_channel_id(
    state: FSMContext,
) -> int | None:
    data = await state.get_data()

    value = data.get(
        "autopost_channel_id"
    )

    if value is None:
        return None

    return int(
        value
    )


def filter_field_label(
    field: str,
) -> str:
    labels = {
        "min_discount_percentage":
            "📉 Sconto minimo",

        "min_score":
            "🎯 Score minimo",

        "min_rating":
            "⭐ Rating minimo",

        "min_reviews":
            "💬 Recensioni minime",

        "min_price":
            "💶 Prezzo minimo",

        "max_price":
            "💰 Prezzo massimo",
    }

    return labels.get(
        field,
        field,
    )


def is_optional_filter(
    field: str,
) -> bool:
    return field in {
        "min_rating",
        "min_reviews",
        "min_price",
        "max_price",
    }


def parse_filter_value(
    field: str,
    raw_value: str,
):
    value = (
        raw_value.strip().lower()
    )

    if (
        is_optional_filter(field)
        and value in {
            "off",
            "no",
            "nessuno",
            "disattiva",
            "-",
        }
    ):
        return None

    normalized = (
        value.replace(
            ",",
            ".",
        )
    )

    if field in {
        "min_score",
        "min_reviews",
    }:
        return int(
            normalized
        )

    return Decimal(
        normalized
    )


# =========================================================
# KEYBOARDS
# =========================================================


def autopost_menu_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "⚙️ Configura canale"
                    ),
                    callback_data=(
                        "autopost:channels"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🧪 Test lista prodotti"
                    ),
                    callback_data=(
                        "autopost:demo_scan"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=(
                        "menu:home"
                    ),
                )
            ],
        ]
    )


def channel_selection_keyboard(
    channels,
) -> InlineKeyboardMarkup:
    rows = []

    for channel in channels:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        "📢 "
                        f"{channel.title[:35]}"
                    ),
                    callback_data=(
                        "autopost:channel:"
                        f"{channel.id}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Autoposting",
                callback_data=(
                    "menu:autopost"
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def channel_config_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "⚡ Attivazione "
                        "e intervalli"
                    ),
                    callback_data=(
                        "autopost:runtime"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗂 Categorie",
                    callback_data=(
                        "autopost:categories"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎛 Filtri",
                    callback_data=(
                        "autopost:filters"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "♻️ Anti-duplicati"
                    ),
                    callback_data=(
                        "autopost:dedupe"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🧪 Pipeline completa"
                    ),
                    callback_data=(
                        "autopost:"
                        "pipeline_test"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "⬅️ Scegli canale"
                    ),
                    callback_data=(
                        "autopost:channels"
                    ),
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=(
                        "menu:home"
                    ),
                ),
            ],
        ]
    )
    
def categories_keyboard(
    selected: tuple[
        str,
        ...
    ],
) -> InlineKeyboardMarkup:
    rows = []

    all_selected = (
        len(selected) == 0
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    (
                        "✅ "
                        if all_selected
                        else "⬜ "
                    )
                    + "Tutte le categorie"
                ),
                callback_data=(
                    "autopost:category_all"
                ),
            )
        ]
    )

    current_row = []

    for category in (
        AUTOPOST_CATEGORIES
    ):
        checked = (
            category.key
            in selected
        )

        current_row.append(
            InlineKeyboardButton(
                text=(
                    (
                        "✅ "
                        if checked
                        else "⬜ "
                    )
                    + category.emoji
                    + " "
                    + category.label
                ),
                callback_data=(
                    "autopost:category:"
                    f"{category.key}"
                ),
            )
        )

        if len(current_row) == 2:
            rows.append(
                current_row
            )

            current_row = []

    if current_row:
        rows.append(
            current_row
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🧪 Test categorie",
                callback_data=(
                    "autopost:category_test"
                ),
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="⬅️ Configurazione",
                callback_data=(
                    "autopost:config_back"
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def filters_keyboard(
    config: ChannelAutopostConfig,
) -> InlineKeyboardMarkup:
    shipping_icon = (
        "✅"
        if config
        .require_amazon_shipping
        else "❌"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "📉 Sconto minimo"
                    ),
                    callback_data=(
                        "autopost:filter:"
                        "min_discount_percentage"
                    ),
                ),
                InlineKeyboardButton(
                    text=(
                        "🎯 Score minimo"
                    ),
                    callback_data=(
                        "autopost:filter:"
                        "min_score"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⭐ Rating minimo",
                    callback_data=(
                        "autopost:filter:"
                        "min_rating"
                    ),
                ),
                InlineKeyboardButton(
                    text=(
                        "💬 Recensioni"
                    ),
                    callback_data=(
                        "autopost:filter:"
                        "min_reviews"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💶 Prezzo minimo",
                    callback_data=(
                        "autopost:filter:"
                        "min_price"
                    ),
                ),
                InlineKeyboardButton(
                    text="💰 Prezzo massimo",
                    callback_data=(
                        "autopost:filter:"
                        "max_price"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=(
                        f"{shipping_icon} "
                        "Solo spediti Amazon"
                    ),
                    callback_data=(
                        "autopost:filter_shipping"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧪 Test filtri",
                    callback_data=(
                        "autopost:filter_test"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "♻️ Ripristina default"
                    ),
                    callback_data=(
                        "autopost:filter_reset"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Configurazione",
                    callback_data=(
                        "autopost:config_back"
                    ),
                )
            ],
        ]
    )


def filter_input_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Filtri",
                    callback_data=(
                        "autopost:filters"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=(
                        "menu:home"
                    ),
                )
            ],
        ]
    )


def category_test_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Categorie",
                    callback_data=(
                        "autopost:categories"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=(
                        "menu:home"
                    ),
                )
            ],
        ]
    )


def filter_test_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Filtri",
                    callback_data=(
                        "autopost:filters"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=(
                        "menu:home"
                    ),
                )
            ],
        ]
    )


def batch_result_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Ripeti test",
                    callback_data=(
                        "autopost:demo_scan"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Autoposting",
                    callback_data=(
                        "menu:autopost"
                    ),
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=(
                        "menu:home"
                    ),
                ),
            ],
        ]
    )


# =========================================================
# TEXT BATCH
# =========================================================


def batch_result_text(
    result: DealBatchResult,
) -> str:
    lines = [
        "🧠 <b>Deal Engine — Batch Test</b>",
        "",
        "🧪 Sorgente: <b>LISTA DEMO</b>",
        "",
        (
            f"🔎 Prodotti analizzati: "
            f"<b>{result.scanned_count}</b>"
        ),
        (
            f"✅ Validi per autopost: "
            f"<b>{result.valid_count}</b>"
        ),
        (
            f"❌ Scartati: "
            f"<b>{result.rejected_count}</b>"
        ),
    ]

    if result.valid_candidates:
        lines.extend(
            [
                "",
                "🏆 <b>Classifica offerte</b>",
                "",
            ]
        )

        medals = (
            "🥇",
            "🥈",
            "🥉",
        )

        for index, candidate in enumerate(
            result.valid_candidates
        ):
            icon = (
                medals[index]
                if index < len(medals)
                else "✅"
            )

            lines.append(
                (
                    f"{icon} <b>"
                    f"{escape(
                        candidate.product.title
                    )}"
                    f"</b>"
                )
            )

            lines.append(
                (
                    f"🎯 "
                    f"{candidate.evaluation.score}"
                    f"/100 • "
                    f"{candidate.evaluation.verdict}"
                )
            )

            lines.append("")

    if result.rejected_candidates:
        lines.extend(
            [
                "🚫 <b>Scartati</b>",
                "",
            ]
        )

        for candidate in (
            result.rejected_candidates
        ):
            lines.append(
                (
                    f"❌ <b>"
                    f"{escape(
                        candidate.product.title
                    )}"
                    f"</b>"
                )
            )

            if candidate.evaluation.blockers:
                lines.append(
                    (
                        "↳ "
                        f"{escape(
                            candidate
                            .evaluation
                            .blockers[0]
                        )}"
                    )
                )

            lines.append("")

    return "\n".join(
        lines
    ).strip()


# =========================================================
# MENU AUTOPOST
# =========================================================


@router.callback_query(
    F.data == "menu:autopost"
)
async def autopost_menu(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    if query.message is not None:
        await query.message.edit_text(
            "🤖 <b>Autoposting</b>"
            "\n\n"
            "🧠 Deal Engine: "
            "<b>ATTIVO</b>\n"
            "📦 Batch Engine: "
            "<b>ATTIVO</b>\n"
            "🗂 Categorie: "
            "<b>ATTIVE</b>\n"
            "🎛 Filtri: "
            "<b>ATTIVI</b>\n"
            "🔎 Provider offerte: "
            "<b>DEMO</b>\n"
            "📤 Auto-pubblicazione: "
            "<b>NON ATTIVA</b>",
            reply_markup=(
                autopost_menu_keyboard()
            ),
        )

    await query.answer()


# =========================================================
# CANALI
# =========================================================


@router.callback_query(
    F.data == "autopost:channels"
)
async def autopost_channels(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channels = await list_channels(
        settings.admin_user_id
    )

    if not channels:
        await query.answer(
            "Nessun canale collegato.",
            show_alert=True,
        )

        return

    if query.message is not None:
        await query.message.edit_text(
            "⚙️ <b>Configura "
            "Autoposting</b>"
            "\n\n"
            "Scegli il canale:",
            reply_markup=(
                channel_selection_keyboard(
                    channels
                )
            ),
        )

    await query.answer()


@router.callback_query(
    F.data.startswith(
        "autopost:channel:"
    )
)
async def autopost_select_channel(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    channel_id = int(
        query.data.split(":")[-1]
    )

    channel = await get_channel(
        channel_id,
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )

        return

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel.id,
        )
    )

    selected = (
        get_selected_categories(
            config
        )
    )

    await state.update_data(
        autopost_channel_id=(
            channel.id
        )
    )

    if query.message is not None:
        await query.message.edit_text(
            "⚙️ <b>Configurazione "
            "Autoposting</b>"
            "\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            f"🗂 Categorie:\n"
            f"<b>"
            f"{escape(
                categories_summary(
                    selected
                )
            )}"
            f"</b>"
            "\n\n"
            "Scegli cosa configurare:",
            reply_markup=(
                channel_config_keyboard()
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "autopost:config_back"
)
async def autopost_config_back(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    channel = await get_channel(
        channel_id,
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )

        return

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel.id,
        )
    )

    selected = (
        get_selected_categories(
            config
        )
    )

    if query.message is not None:
        await query.message.edit_text(
            "⚙️ <b>Configurazione "
            "Autoposting</b>"
            "\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            f"🗂 Categorie:\n"
            f"<b>"
            f"{escape(
                categories_summary(
                    selected
                )
            )}"
            f"</b>"
            "\n\n"
            "🎛 Filtri configurabili "
            "indipendentemente "
            "per questo canale.",
            reply_markup=(
                channel_config_keyboard()
            ),
        )

    await query.answer()


# =========================================================
# CATEGORIE
# =========================================================


@router.callback_query(
    F.data == "autopost:categories"
)
async def autopost_categories(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Seleziona prima un canale.",
            show_alert=True,
        )

        return

    channel = await get_channel(
        channel_id,
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )

        return

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel.id,
        )
    )

    selected = (
        get_selected_categories(
            config
        )
    )

    if query.message is not None:
        await query.message.edit_text(
            "🗂 <b>Categorie "
            "Autoposting</b>"
            "\n\n"
            f"📢 "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Seleziona una o più "
            "categorie.\n\n"
            "ℹ️ Nessuna categoria "
            "specifica = "
            "<b>Tutte</b>.",
            reply_markup=(
                categories_keyboard(
                    selected
                )
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "autopost:category_all"
)
async def autopost_category_all(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    config = (
        await set_selected_categories(
            settings.admin_user_id,
            channel_id,
            (),
        )
    )

    if query.message is not None:
        await query.message.edit_reply_markup(
            reply_markup=(
                categories_keyboard(
                    get_selected_categories(
                        config
                    )
                )
            )
        )

    await query.answer(
        "Tutte le categorie."
    )


@router.callback_query(
    F.data.startswith(
        "autopost:category:"
    )
)
async def autopost_toggle_category(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    category_key = (
        query.data.split(":")[-1]
    )

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    selected = list(
        get_selected_categories(
            config
        )
    )

    if category_key in selected:
        selected.remove(
            category_key
        )

    else:
        selected.append(
            category_key
        )

    config = (
        await set_selected_categories(
            settings.admin_user_id,
            channel_id,
            selected,
        )
    )

    if query.message is not None:
        await query.message.edit_reply_markup(
            reply_markup=(
                categories_keyboard(
                    get_selected_categories(
                        config
                    )
                )
            )
        )

    await query.answer(
        "Categorie aggiornate."
    )


@router.callback_query(
    F.data == "autopost:category_test"
)
async def autopost_category_test(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    selected = (
        get_selected_categories(
            config
        )
    )

    all_products = (
        build_demo_products()
    )

    filtered_products = (
        filter_products_by_categories(
            all_products,
            selected,
        )
    )

    result = evaluate_products(
        filtered_products
    )

    text = (
        "🧪 <b>Test categorie</b>"
        "\n\n"
        f"🗂 Selezione:\n"
        f"<b>"
        f"{escape(
            categories_summary(
                selected
            )
        )}"
        f"</b>"
        "\n\n"
        f"📦 Totali: "
        f"<b>{len(all_products)}</b>"
        "\n"
        f"🔎 Dopo categorie: "
        f"<b>{len(filtered_products)}</b>"
        "\n"
        f"✅ Deal validi: "
        f"<b>{result.valid_count}</b>"
        "\n"
        f"❌ Deal scartati: "
        f"<b>{result.rejected_count}</b>"
    )

    if query.message is not None:
        await query.message.edit_text(
            text,
            reply_markup=(
                category_test_keyboard()
            ),
        )

    await query.answer()


# =========================================================
# FILTRI MENU
# =========================================================


@router.callback_query(
    F.data == "autopost:filters"
)
async def autopost_filters_menu(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Seleziona prima un canale.",
            show_alert=True,
        )

        return

    channel = await get_channel(
        channel_id,
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )

        return

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    await state.set_state(
        None
    )

    if query.message is not None:
        await query.message.edit_text(
            "🎛 <b>Filtri "
            "Autoposting</b>"
            "\n\n"
            f"📢 "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            f"{filters_summary(config)}"
            "\n\n"
            "Premi un filtro "
            "per modificarlo.",
            reply_markup=(
                filters_keyboard(
                    config
                )
            ),
        )

    await query.answer()


# =========================================================
# MODIFICA FILTRO NUMERICO
# =========================================================


@router.callback_query(
    F.data.startswith(
        "autopost:filter:"
    )
)
async def autopost_edit_filter(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    field = (
        query.data.split(":")[-1]
    )

    allowed_fields = {
        "min_discount_percentage",
        "min_score",
        "min_rating",
        "min_reviews",
        "min_price",
        "max_price",
    }

    if field not in allowed_fields:
        await query.answer(
            "Filtro non valido.",
            show_alert=True,
        )

        return

    await state.update_data(
        autopost_filter_field=(
            field
        )
    )

    await state.set_state(
        AutopostFilterStates
        .waiting_value
    )

    optional_text = ""

    if is_optional_filter(
        field
    ):
        optional_text = (
            "\n\nPer disattivare "
            "questo filtro invia:\n"
            "<code>off</code>"
        )

    examples = {
        "min_discount_percentage":
            "20",

        "min_score":
            "70",

        "min_rating":
            "4,5",

        "min_reviews":
            "100",

        "min_price":
            "20",

        "max_price":
            "150",
    }

    if query.message is not None:
        await query.message.edit_text(
            f"{filter_field_label(field)}"
            "\n\n"
            "Invia il nuovo valore."
            "\n\n"
            "Esempio:\n"
            f"<code>"
            f"{examples[field]}"
            f"</code>"
            f"{optional_text}",
            reply_markup=(
                filter_input_keyboard()
            ),
        )

    await query.answer()


@router.message(
    AutopostFilterStates
    .waiting_value
)
async def receive_filter_value(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.text:
        await message.answer(
            "❌ Invia un valore "
            "come testo."
        )

        return

    settings = get_settings()

    data = await state.get_data()

    channel_id = data.get(
        "autopost_channel_id"
    )

    field = data.get(
        "autopost_filter_field"
    )

    if (
        channel_id is None
        or field is None
    ):
        await state.clear()

        await message.answer(
            "❌ Sessione scaduta."
        )

        return

    try:
        value = parse_filter_value(
            str(field),
            message.text,
        )

        config = (
            await set_autopost_filter(
                settings.admin_user_id,
                int(channel_id),
                str(field),
                value,
            )
        )

    except (
        ValueError,
        InvalidOperation,
    ) as exc:
        await message.answer(
            "❌ Valore non valido."
            "\n\n"
            f"{escape(str(exc))}",
            reply_markup=(
                filter_input_keyboard()
            ),
        )

        return

    await state.set_state(
        None
    )

    await state.update_data(
        autopost_filter_field=None
    )

    await message.answer(
        "✅ <b>Filtro aggiornato</b>"
        "\n\n"
        f"{filters_summary(config)}",
        reply_markup=(
            filters_keyboard(
                config
            )
        ),
    )


# =========================================================
# SPEDIZIONE AMAZON
# =========================================================


@router.callback_query(
    F.data
    == "autopost:filter_shipping"
)
async def toggle_amazon_shipping(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    config = await set_autopost_filter(
        settings.admin_user_id,
        channel_id,
        "require_amazon_shipping",
        not bool(
            config
            .require_amazon_shipping
        ),
    )

    if query.message is not None:
        await query.message.edit_text(
            "🎛 <b>Filtri "
            "Autoposting</b>"
            "\n\n"
            f"{filters_summary(config)}",
            reply_markup=(
                filters_keyboard(
                    config
                )
            ),
        )

    await query.answer(
        "Filtro aggiornato."
    )


# =========================================================
# RESET FILTRI
# =========================================================


@router.callback_query(
    F.data
    == "autopost:filter_reset"
)
async def reset_filters(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    config = (
        await reset_autopost_filters(
            settings.admin_user_id,
            channel_id,
        )
    )

    if query.message is not None:
        await query.message.edit_text(
            "♻️ <b>Filtri "
            "ripristinati</b>"
            "\n\n"
            f"{filters_summary(config)}",
            reply_markup=(
                filters_keyboard(
                    config
                )
            ),
        )

    await query.answer(
        "Default ripristinati."
    )


# =========================================================
# TEST FILTRI
# =========================================================


@router.callback_query(
    F.data == "autopost:filter_test"
)
async def test_filters(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = (
        await get_config_channel_id(
            state
        )
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    channel = await get_channel(
        channel_id,
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )

        return

    config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    selected_categories = (
        get_selected_categories(
            config
        )
    )

    all_products = (
        build_demo_products()
    )

    category_products = (
        filter_products_by_categories(
            all_products,
            selected_categories,
        )
    )

    rules = config_to_rules(
        config
    )

    result: ChannelPipelineResult = (
        filter_and_evaluate_products(
            category_products,
            rules,
        )
    )

    text = (
        "🧪 <b>Test filtri "
        "Autoposting</b>"
        "\n\n"
        f"📢 "
        f"<b>{escape(channel.title)}</b>"
        "\n\n"
        f"{filters_summary(config)}"
        "\n\n"
        "────────────────"
        "\n\n"
        f"📦 Prodotti demo totali: "
        f"<b>{len(all_products)}</b>"
        "\n"
        f"🗂 Dopo categorie: "
        f"<b>{len(category_products)}</b>"
        "\n"
        f"🎛 Passano i filtri: "
        f"<b>"
        f"{result.filter_passed_count}"
        f"</b>"
        "\n"
        f"🚫 Scartati dai filtri: "
        f"<b>"
        f"{result.filter_rejected_count}"
        f"</b>"
        "\n"
        f"✅ Validi Deal Engine: "
        f"<b>"
        f"{result.deal_result.valid_count}"
        f"</b>"
        "\n"
        f"❌ Scartati Deal Engine: "
        f"<b>"
        f"{result.deal_result.rejected_count}"
        f"</b>"
    )

    if result.rejected_by_filters:
        text += (
            "\n\n"
            "🚫 <b>Scartati "
            "dai filtri:</b>"
        )

        for rejected in (
            result.rejected_by_filters
        ):
            text += (
                "\n\n• "
                f"<b>"
                f"{escape(
                    rejected.product.title
                )}"
                f"</b>"
            )

            if rejected.reasons:
                text += (
                    "\n↳ "
                    f"{escape(
                        rejected.reasons[0]
                    )}"
                )

    if result.deal_result.valid_candidates:
        text += (
            "\n\n"
            "🏆 <b>Offerte finali:</b>"
        )

        for candidate in (
            result
            .deal_result
            .valid_candidates
        ):
            text += (
                "\n• "
                f"{escape(
                    candidate.product.title
                )}"
                f" — "
                f"{candidate.evaluation.score}"
                f"/100"
            )

    if query.message is not None:
        await query.message.edit_text(
            text,
            reply_markup=(
                filter_test_keyboard()
            ),
        )

    await query.answer(
        "Test completato."
    )


# =========================================================
# BATCH GENERALE
# =========================================================


@router.callback_query(
    F.data == "autopost:demo_scan"
)
async def demo_scan(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()

    products = (
        build_demo_products()
    )

    result = evaluate_products(
        products
    )

    if query.message is not None:
        await query.message.edit_text(
            batch_result_text(
                result
            ),
            reply_markup=(
                batch_result_keyboard()
            ),
        )

    await query.answer(
        (
            f"Analizzati "
            f"{result.scanned_count} "
            f"prodotti."
        )
    )
