from datetime import timezone
from html import escape
from zoneinfo import ZoneInfo

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

from app.autopost_store import (
    get_or_create_autopost_config,
)
from app.autoposting import (
    build_demo_products,
)
from app.config import get_settings
from app.database import get_channel
from app.dedupe_store import (
    clear_test_publications,
    filter_recent_duplicates,
    record_publication,
    set_dedupe_window_hours,
)


router = Router(
    name="dedupe"
)


# =========================================================
# HELPERS
# =========================================================


async def get_channel_id(
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


def window_text(
    hours: int,
) -> str:
    if hours <= 0:
        return "❌ DISATTIVATO"

    if hours % 24 == 0:
        days = hours // 24

        if days == 1:
            return "1 giorno"

        return (
            f"{days} giorni"
        )

    return (
        f"{hours} ore"
    )


# =========================================================
# KEYBOARD
# =========================================================


def dedupe_keyboard(
    current_hours: int,
) -> InlineKeyboardMarkup:
    def label(
        hours: int,
        text: str,
    ) -> str:
        prefix = (
            "✅ "
            if current_hours
            == hours
            else ""
        )

        return (
            prefix + text
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label(
                        0,
                        "OFF",
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_set:0"
                    ),
                ),
                InlineKeyboardButton(
                    text=label(
                        24,
                        "1 giorno",
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_set:24"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=label(
                        72,
                        "3 giorni",
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_set:72"
                    ),
                ),
                InlineKeyboardButton(
                    text=label(
                        168,
                        "7 giorni",
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_set:168"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=label(
                        336,
                        "14 giorni",
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_set:336"
                    ),
                ),
                InlineKeyboardButton(
                    text=label(
                        720,
                        "30 giorni",
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_set:720"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🧪 Test anti-duplicati"
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_test"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "📝 Simula "
                        "pubblicazione demo"
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_record_demo"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🧹 Pulisci "
                        "record DEMO"
                    ),
                    callback_data=(
                        "autopost:"
                        "dedupe_clear_test"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "⬅️ Configurazione"
                    ),
                    callback_data=(
                        "autopost:"
                        "config_back"
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
# MENU
# =========================================================


@router.callback_query(
    F.data == "autopost:dedupe"
)
async def dedupe_menu(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = await get_channel_id(
        state
    )

    if channel_id is None:
        await query.answer(
            "Seleziona prima "
            "un canale.",
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

    hours = int(
        config.dedupe_window_hours
    )

    if query.message is not None:
        await query.message.edit_text(
            "♻️ <b>Anti-duplicati</b>"
            "\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Un ASIN già pubblicato "
            "in questo canale viene "
            "escluso per la durata "
            "selezionata."
            "\n\n"
            f"⏱ Finestra attuale: "
            f"<b>{window_text(hours)}</b>"
            "\n\n"
            "ℹ️ Il controllo è "
            "indipendente per ogni "
            "canale.",
            reply_markup=(
                dedupe_keyboard(
                    hours
                )
            ),
        )

    await query.answer()


# =========================================================
# CAMBIA FINESTRA
# =========================================================


@router.callback_query(
    F.data.startswith(
        "autopost:dedupe_set:"
    )
)
async def change_dedupe_window(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    channel_id = await get_channel_id(
        state
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    hours = int(
        query.data.split(":")[-1]
    )

    config = (
        await set_dedupe_window_hours(
            settings.admin_user_id,
            channel_id,
            hours,
        )
    )

    if query.message is not None:
        await query.message.edit_text(
            "♻️ <b>Anti-duplicati</b>"
            "\n\n"
            f"⏱ Finestra attuale: "
            f"<b>"
            f"{window_text(
                int(
                    config
                    .dedupe_window_hours
                )
            )}"
            f"</b>"
            "\n\n"
            "✅ Configurazione salvata.",
            reply_markup=(
                dedupe_keyboard(
                    int(
                        config
                        .dedupe_window_hours
                    )
                )
            ),
        )

    await query.answer(
        "Finestra aggiornata."
    )


# =========================================================
# SIMULA PUBBLICAZIONE
# =========================================================


@router.callback_query(
    F.data
    == "autopost:dedupe_record_demo"
)
async def record_demo_publication(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = await get_channel_id(
        state
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    products = build_demo_products()

    product = products[0]

    await record_publication(
        owner_telegram_user_id=(
            settings.admin_user_id
        ),
        channel_id=channel_id,
        product=product,
        source="test",
    )

    await query.answer(
        (
            f"{product.asin} "
            "registrato come "
            "pubblicazione DEMO."
        ),
        show_alert=True,
    )


# =========================================================
# TEST
# =========================================================


@router.callback_query(
    F.data == "autopost:dedupe_test"
)
async def test_dedupe(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = await get_channel_id(
        state
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

    products = build_demo_products()

    result = (
        await filter_recent_duplicates(
            owner_telegram_user_id=(
                settings.admin_user_id
            ),
            channel_id=channel_id,
            products=products,
            window_hours=int(
                config
                .dedupe_window_hours
            ),
        )
    )

    text = (
        "🧪 <b>Test "
        "Anti-duplicati</b>"
        "\n\n"
        f"📢 Canale: "
        f"<b>{escape(channel.title)}</b>"
        "\n"
        f"⏱ Finestra: "
        f"<b>"
        f"{window_text(
            int(
                config
                .dedupe_window_hours
            )
        )}"
        f"</b>"
        "\n\n"
        f"📦 Prodotti analizzati: "
        f"<b>{result.total_count}</b>"
        "\n"
        f"✅ Passano: "
        f"<b>{result.passed_count}</b>"
        "\n"
        f"♻️ Duplicati esclusi: "
        f"<b>{result.duplicate_count}</b>"
    )

    if result.duplicate_products:
        timezone_local = ZoneInfo(
            settings.app_timezone
        )

        text += (
            "\n\n"
            "🚫 <b>Duplicati:</b>"
        )

        for duplicate in (
            result.duplicate_products
        ):
            local_time = (
                duplicate
                .last_published_at
                .astimezone(
                    timezone_local
                )
            )

            text += (
                "\n\n• "
                f"<b>"
                f"{escape(
                    duplicate
                    .product
                    .title
                )}"
                f"</b>"
                "\n"
                f"🔢 "
                f"<code>"
                f"{escape(
                    duplicate
                    .product
                    .asin
                )}"
                f"</code>"
                "\n"
                f"🕒 Ultima: "
                f"{local_time.strftime(
                    '%d/%m/%Y %H:%M'
                )}"
            )

    if query.message is not None:
        await query.message.edit_text(
            text,
            reply_markup=(
                dedupe_keyboard(
                    int(
                        config
                        .dedupe_window_hours
                    )
                )
            ),
        )

    await query.answer(
        "Controllo completato."
    )


# =========================================================
# PULIZIA SOLO DEMO
# =========================================================


@router.callback_query(
    F.data
    == "autopost:dedupe_clear_test"
)
async def clear_demo_history(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    channel_id = await get_channel_id(
        state
    )

    if channel_id is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    deleted = (
        await clear_test_publications(
            settings.admin_user_id,
            channel_id,
        )
    )

    await query.answer(
        (
            f"Rimossi "
            f"{deleted} record DEMO."
        ),
        show_alert=True,
    )
