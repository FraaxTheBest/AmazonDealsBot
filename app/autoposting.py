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
    Simula una lista ricevuta
    in futuro dal provider.

    NON sono prodotti Amazon reali.
    """

    excellent = ProductSnapshot(
        asin="B0DEMO0001",
        title=(
            "DEMO - Offerta eccellente"
        ),
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0DEMO0001"
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
            "DEMO - Offerta buona"
        ),
        detail_url=(
            "https://www.amazon.it/"
            "dp/B0DEMO0002"
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
                "DEMO - Sconto troppo basso"
            ),
            detail_url=(
                "https://www.amazon.it/"
                "dp/B0DEMO0003"
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
                "DEMO - Prodotto "
                "non disponibile"
            ),
            detail_url=(
                "https://www.amazon.it/"
                "dp/B0DEMO0004"
            ),
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
                "DEMO - Prezzo mancante"
            ),
            detail_url=(
                "https://www.amazon.it/"
                "dp/B0DEMO0005"
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
# KEYBOARDS
# =========================================================


def autopost_menu_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
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


def batch_result_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "🔄 Ripeti test"
                    ),
                    callback_data=(
                        "autopost:demo_scan"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "⬅️ Autoposting"
                    ),
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
        (
            "🧪 Sorgente: "
            "<b>LISTA DEMO</b>"
        ),
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

            if index < len(
                medals
            ):
                icon = medals[
                    index
                ]

            else:
                icon = "✅"

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

            lines.append(
                ""
            )

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
                    f"❌ "
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
                first_blocker = (
                    evaluation.blockers[
                        0
                    ]
                )

                lines.append(
                    (
                        "↳ "
                        f"{escape(first_blocker)}"
                    )
                )

            lines.append(
                ""
            )

    lines.extend(
        [
            "────────────────",
            "",
            (
                "ℹ️ Questa schermata "
                "non pubblica nulla."
            ),
            (
                "Serve a dimostrare che "
                "il motore può ricevere "
                "una lista di prodotti, "
                "filtrarli e ordinarli."
            ),
        ]
    )

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
            "🔎 Provider offerte: "
            "<b>DEMO</b>\n"
            "📤 Pubblicazione automatica: "
            "<b>NON ATTIVA</b>"
            "\n\n"
            "Per la Fase 8C possiamo "
            "simulare la scansione di "
            "una lista di prodotti.",
            reply_markup=(
                autopost_menu_keyboard()
            ),
        )

    await query.answer()


# =========================================================
# DEMO SCAN
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
