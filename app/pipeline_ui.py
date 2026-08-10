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

from app.autopost_pipeline import (
    FullAutopostPipelineResult,
    run_channel_autopost_pipeline,
)
from app.autoposting import (
    build_demo_products,
)
from app.categories import (
    categories_summary,
)
from app.config import get_settings
from app.database import get_channel


router = Router(
    name="pipeline"
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
        return "OFF"

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


def pipeline_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "🔄 Ripeti pipeline"
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
                        "♻️ Anti-duplicati"
                    ),
                    callback_data=(
                        "autopost:dedupe"
                    ),
                ),
                InlineKeyboardButton(
                    text="🎛 Filtri",
                    callback_data=(
                        "autopost:filters"
                    ),
                ),
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
                    text=(
                        "⬅️ Configurazione"
                    ),
                    callback_data=(
                        "autopost:config_back"
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


def build_pipeline_text(
    result: FullAutopostPipelineResult,
    channel_title: str,
    timezone_name: str,
) -> str:
    lines = [
        (
            "🧪 <b>Pipeline "
            "Autoposting completa</b>"
        ),
        "",
        (
            f"📢 Canale: "
            f"<b>"
            f"{escape(channel_title)}"
            f"</b>"
        ),
        "",
        (
            "🗂 Categorie:\n"
            f"<b>"
            f"{escape(
                categories_summary(
                    result
                    .selected_categories
                )
            )}"
            f"</b>"
        ),
        "",
        (
            f"♻️ Anti-duplicati: "
            f"<b>"
            f"{window_text(
                result
                .dedupe_window_hours
            )}"
            f"</b>"
        ),
        "",
        "────────────────",
        "",
        (
            f"📦 Provider / sorgente: "
            f"<b>{result.source_count}</b>"
        ),
        "",
        (
            f"🗂 Dopo categorie: "
            f"<b>"
            f"{result.category_passed_count}"
            f"</b>"
        ),
        (
            f"↳ Scartati categorie: "
            f"<b>"
            f"{result.category_rejected_count}"
            f"</b>"
        ),
        "",
        (
            f"🎛 Passano i filtri: "
            f"<b>"
            f"{result.filter_passed_count}"
            f"</b>"
        ),
        (
            f"↳ Scartati filtri: "
            f"<b>"
            f"{result.filter_rejected_count}"
            f"</b>"
        ),
        "",
        (
            f"🧠 Deal Engine validi: "
            f"<b>"
            f"{result.deal_valid_count}"
            f"</b>"
        ),
        (
            f"↳ Scartati Deal Engine: "
            f"<b>"
            f"{result.deal_rejected_count}"
            f"</b>"
        ),
        "",
        (
            f"♻️ Duplicati esclusi: "
            f"<b>"
            f"{result.duplicate_count}"
            f"</b>"
        ),
        "",
        (
            f"🏆 CANDIDATI FINALI: "
            f"<b>"
            f"{result.final_count}"
            f"</b>"
        ),
    ]

    # =====================================================
    # FINALISTI
    # =====================================================

    if result.final_candidates:
        lines.extend(
            [
                "",
                "🏆 <b>Ranking finale</b>",
                "",
            ]
        )

        medals = (
            "🥇",
            "🥈",
            "🥉",
        )

        for index, candidate in enumerate(
            result.final_candidates
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
                        f"{evaluation
                        .discount_percentage}%"
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

    else:
        lines.extend(
            [
                "",
                (
                    "📭 Nessun prodotto "
                    "ha superato tutta "
                    "la pipeline."
                ),
            ]
        )

    # =====================================================
    # DUPLICATI
    # =====================================================

    if (
        result
        .dedupe_result
        .duplicate_products
    ):
        lines.extend(
            [
                "",
                "♻️ <b>Duplicati rimossi</b>",
                "",
            ]
        )

        timezone_local = ZoneInfo(
            timezone_name
        )

        for duplicate in (
            result
            .dedupe_result
            .duplicate_products
        ):
            local_time = (
                duplicate
                .last_published_at
                .astimezone(
                    timezone_local
                )
            )

            lines.append(
                (
                    f"• "
                    f"<b>"
                    f"{escape(
                        duplicate
                        .product
                        .title
                    )}"
                    f"</b>"
                )
            )

            lines.append(
                (
                    f"🔢 "
                    f"<code>"
                    f"{escape(
                        duplicate
                        .product
                        .asin
                    )}"
                    f"</code>"
                )
            )

            lines.append(
                (
                    f"🕒 Ultima pubblicazione: "
                    f"{local_time.strftime(
                        '%d/%m/%Y %H:%M'
                    )}"
                )
            )

            lines.append("")

    # =====================================================
    # FILTRI SCARTATI
    # =====================================================

    if (
        result
        .filter_result
        .rejected_by_filters
    ):
        lines.extend(
            [
                "",
                "🎛 <b>Scartati dai filtri</b>",
                "",
            ]
        )

        for rejected in (
            result
            .filter_result
            .rejected_by_filters
        ):
            lines.append(
                (
                    "• "
                    f"<b>"
                    f"{escape(
                        rejected
                        .product
                        .title
                    )}"
                    f"</b>"
                )
            )

            if rejected.reasons:
                lines.append(
                    (
                        "↳ "
                        f"{escape(
                            rejected
                            .reasons[0]
                        )}"
                    )
                )

            lines.append("")

    # =====================================================
    # DEAL ENGINE SCARTATI
    # =====================================================

    if (
        result
        .filter_result
        .deal_result
        .rejected_candidates
    ):
        lines.extend(
            [
                "",
                (
                    "🧠 <b>Scartati "
                    "dal Deal Engine</b>"
                ),
                "",
            ]
        )

        for candidate in (
            result
            .filter_result
            .deal_result
            .rejected_candidates
        ):
            lines.append(
                (
                    "• "
                    f"<b>"
                    f"{escape(
                        candidate
                        .product
                        .title
                    )}"
                    f"</b>"
                )
            )

            if (
                candidate
                .evaluation
                .blockers
            ):
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

    lines.extend(
        [
            "",
            "────────────────",
            "",
            (
                "ℹ️ Test diagnostico: "
                "<b>nessun post viene "
                "pubblicato.</b>"
            ),
        ]
    )

    return "\n".join(
        lines
    ).strip()


# =========================================================
# PIPELINE TEST
# =========================================================


@router.callback_query(
    F.data == "autopost:pipeline_test"
)
async def pipeline_test(
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

    products = (
        build_demo_products()
    )

    try:
        result = (
            await run_channel_autopost_pipeline(
                owner_telegram_user_id=(
                    settings.admin_user_id
                ),
                channel_id=channel.id,
                products=products,
            )
        )

    except ValueError as exc:
        await query.answer(
            str(exc),
            show_alert=True,
        )

        return

    if query.message is not None:
        await query.message.edit_text(
            build_pipeline_text(
                result=result,
                channel_title=(
                    channel.title
                ),
                timezone_name=(
                    settings.app_timezone
                ),
            ),
            reply_markup=(
                pipeline_keyboard()
            ),
        )

    await query.answer(
        (
            f"Pipeline completata: "
            f"{result.final_count} "
            f"candidati finali."
        )
    )
