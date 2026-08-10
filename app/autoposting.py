from decimal import Decimal
from html import escape

from aiogram import (
    F,
    Router,
)
from aiogram.fsm.context import (
    FSMContext,
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from app.amazon.models import (
    ProductSnapshot,
)
from app.autopost_store import (
    get_or_create_autopost_config,
    get_selected_categories,
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


# =========================================================
# DEMO PRODUCTS
# =========================================================


def build_demo_products(
) -> list[
    ProductSnapshot
]:
    """
    Simula prodotti provenienti
    dal provider.

    Le categorie sono interne
    al bot.
    """

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
        category_key=(
            "electronics"
        ),
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
        category_key=(
            "home_kitchen"
        ),
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

    weak_discount = (
        ProductSnapshot(
            asin="B0DEMO0003",
            title=(
                "DEMO - Elettronica "
                "sconto basso"
            ),
            detail_url=(
                "https://www.amazon.it/"
                "dp/B0DEMO0003"
            ),
            category_key=(
                "electronics"
            ),
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
    )

    unavailable = (
        ProductSnapshot(
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
    )

    missing_price = (
        ProductSnapshot(
            asin="B0DEMO0005",
            title=(
                "DEMO - Casa "
                "prezzo mancante"
            ),
            detail_url=(
                "https://www.amazon.it/"
                "dp/B0DEMO0005"
            ),
            category_key=(
                "home_kitchen"
            ),
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
    )

    return [
        excellent,
        good,
        weak_discount,
        unavailable,
        missing_price,
    ]


# =========================================================
# GENERIC KEYBOARDS
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
                        "🗂 Categorie"
                    ),
                    callback_data=(
                        "autopost:categories"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🎛 Filtri"
                    ),
                    callback_data=(
                        "autopost:filters_future"
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

        text = (
            (
                "✅ "
                if checked
                else "⬜ "
            )
            + category.emoji
            + " "
            + category.label
        )

        current_row.append(
            InlineKeyboardButton(
                text=text,
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
                text=(
                    "🧪 Test categorie"
                ),
                callback_data=(
                    "autopost:category_test"
                ),
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text=(
                    "⬅️ Configurazione"
                ),
                callback_data=(
                    "autopost:config_back"
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
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
# TEXT
# =========================================================


def batch_result_text(
    result: DealBatchResult,
) -> str:
    lines = [
        (
            "🧠 <b>Deal Engine "
            "— Batch Test</b>"
        ),
        "",
        "🧪 Sorgente: "
        "<b>LISTA DEMO</b>",
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
            product = (
                candidate.product
            )

            evaluation = (
                candidate.evaluation
            )

            icon = (
                medals[index]
                if index < len(medals)
                else "✅"
            )

            lines.append(
                (
                    f"{icon} "
                    f"<b>"
                    f"{escape(product.title)}"
                    f"</b>"
                )
            )

            lines.append(
                (
                    f"🎯 "
                    f"{evaluation.score}/100 "
                    f"• "
                    f"{evaluation.verdict}"
                )
            )

            if (
                evaluation
                .discount_percentage
                is not None
            ):
                lines.append(
                    (
                        f"📉 "
                        f"{evaluation.discount_percentage}%"
                    )
                )

            lines.append(
                (
                    f"🔢 "
                    f"<code>"
                    f"{escape(product.asin)}"
                    f"</code>"
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
            product = (
                candidate.product
            )

            evaluation = (
                candidate.evaluation
            )

            lines.append(
                (
                    "❌ "
                    f"<b>"
                    f"{escape(product.title)}"
                    f"</b>"
                )
            )

            lines.append(
                (
                    f"🎯 "
                    f"{evaluation.score}/100"
                )
            )

            if evaluation.blockers:
                lines.append(
                    (
                        "↳ "
                        f"{escape(
                            evaluation
                            .blockers[0]
                        )}"
                    )
                )

            lines.append("")

    return "\n".join(
        lines
    ).strip()


# =========================================================
# STATE HELPERS
# =========================================================


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


# =========================================================
# AUTOPOST MENU
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
# SELEZIONE CANALE
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
            f"</b>",
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
            "ℹ️ Se scegli "
            "<b>Tutte le categorie</b>, "
            "nessun filtro categoria "
            "verrà applicato.",
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

    selected = (
        get_selected_categories(
            config
        )
    )

    if query.message is not None:
        await query.message.edit_reply_markup(
            reply_markup=(
                categories_keyboard(
                    selected
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

    selected_tuple = (
        get_selected_categories(
            config
        )
    )

    if query.message is not None:
        await query.message.edit_reply_markup(
            reply_markup=(
                categories_keyboard(
                    selected_tuple
                )
            )
        )

    await query.answer(
        "Categorie aggiornate."
    )


# =========================================================
# TEST CATEGORIE
# =========================================================


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
        f"📢 Canale: "
        f"<b>{escape(channel.title)}</b>"
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
        f"📦 Prodotti demo totali: "
        f"<b>{len(all_products)}</b>"
        "\n"
        f"🔎 Dopo filtro categorie: "
        f"<b>{len(filtered_products)}</b>"
        "\n"
        f"✅ Validati dal Deal Engine: "
        f"<b>{result.valid_count}</b>"
        "\n"
        f"❌ Scartati dal Deal Engine: "
        f"<b>{result.rejected_count}</b>"
    )

    if filtered_products:
        text += (
            "\n\n"
            "📋 <b>Prodotti passati "
            "al Deal Engine:</b>"
        )

        for product in (
            filtered_products
        ):
            text += (
                "\n• "
                f"{escape(product.title)}"
            )

    if query.message is not None:
        await query.message.edit_text(
            text,
            reply_markup=(
                category_test_keyboard()
            ),
        )

    await query.answer(
        "Test completato."
    )


# =========================================================
# FILTRI FUTURI
# =========================================================


@router.callback_query(
    F.data
    == "autopost:filters_future"
)
async def autopost_filters_future(
    query: CallbackQuery,
) -> None:
    await query.answer(
        "🎛 I filtri arrivano "
        "nella Fase 9B.",
        show_alert=True,
    )


# =========================================================
# DEMO BATCH GENERALE
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
