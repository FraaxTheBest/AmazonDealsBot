from decimal import Decimal
from html import escape

from aiogram import (
    Bot,
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

from app.autopost_publish_service import (
    publish_approved_candidate,
)
from app.autopost_queue_store import (
    AutopostCandidate,
    STATUS_APPROVED,
    approve_candidate,
    get_owner_candidate,
    list_owner_pending_candidates,
    reject_candidate,
    restore_candidate_pending,
)
from app.config import get_settings
from app.database import Channel


router = Router(
    name="autopost_queue"
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


def money(
    value: Decimal | None,
) -> str:
    if value is None:
        return "N/D"

    return (
        f"{value:.2f}"
        .replace(".", ",")
        + "€"
    )


def percentage(
    value: Decimal | None,
) -> str:
    if value is None:
        return "N/D"

    if value == value.to_integral():
        return (
            f"{int(value)}%"
        )

    return (
        f"{value:.1f}"
        .replace(".", ",")
        + "%"
    )


def pending_text(
    candidate: AutopostCandidate,
    channel: Channel,
    position: int,
    total: int,
) -> str:
    return (
        "📥 <b>Coda Autopost</b>"
        "\n\n"
        f"📍 Candidato "
        f"<b>{position}/{total}</b>"
        "\n"
        f"📢 Canale: "
        f"<b>{escape(channel.title)}</b>"
        "\n\n"
        f"👀 <b>"
        f"{escape(candidate.title)}"
        f"</b>"
        "\n\n"
        f"💰 Prezzo: "
        f"<b>"
        f"{money(candidate.current_price)}"
        f"</b>"
        "\n"
        f"🏷 Prezzo originale: "
        f"{money(candidate.original_price)}"
        "\n"
        f"📉 Sconto: "
        f"<b>"
        f"{percentage(
            candidate
            .discount_percentage
        )}"
        f"</b>"
        "\n"
        f"💶 Risparmio: "
        f"{money(
            candidate
            .savings_amount
        )}"
        "\n\n"
        f"🧠 Score: "
        f"<b>{candidate.score}/100</b>"
        "\n"
        f"🏆 Giudizio: "
        f"<b>"
        f"{escape(candidate.verdict)}"
        f"</b>"
        "\n"
        f"🔢 ASIN: "
        f"<code>"
        f"{escape(candidate.asin)}"
        f"</code>"
        "\n\n"
        "⏳ Stato: "
        "<b>IN ATTESA DI APPROVAZIONE</b>"
    )


def approved_text(
    candidate: AutopostCandidate,
    channel: Channel,
) -> str:
    return (
        "✅ <b>Candidato approvato</b>"
        "\n\n"
        f"📢 Canale: "
        f"<b>{escape(channel.title)}</b>"
        "\n\n"
        f"👀 <b>"
        f"{escape(candidate.title)}"
        f"</b>"
        "\n\n"
        f"💰 Prezzo: "
        f"<b>"
        f"{money(candidate.current_price)}"
        f"</b>"
        "\n"
        f"📉 Sconto: "
        f"<b>"
        f"{percentage(
            candidate
            .discount_percentage
        )}"
        f"</b>"
        "\n"
        f"🧠 Score: "
        f"<b>{candidate.score}/100</b>"
        "\n\n"
        "✅ Stato: <b>APPROVATO</b>"
        "\n\n"
        "Premi <b>Pubblica ora</b> "
        "per inviarlo realmente "
        "nel canale."
    )


# =========================================================
# KEYBOARDS
# =========================================================


def pending_keyboard(
    candidate_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Approva",
                    callback_data=(
                        "autopost:"
                        "queue_approve:"
                        f"{candidate_id}"
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ Scarta",
                    callback_data=(
                        "autopost:"
                        "queue_reject:"
                        f"{candidate_id}"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⏭ Prossima",
                    callback_data=(
                        "autopost:queue_next"
                    ),
                ),
                InlineKeyboardButton(
                    text="🔄 Aggiorna",
                    callback_data=(
                        "autopost:queue"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Configurazione",
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


def approved_keyboard(
    candidate_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Pubblica ora",
                    callback_data=(
                        "autopost:"
                        "queue_publish:"
                        f"{candidate_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "↩️ Torna in attesa"
                    ),
                    callback_data=(
                        "autopost:"
                        "queue_restore:"
                        f"{candidate_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📥 Torna alla coda",
                    callback_data=(
                        "autopost:queue"
                    ),
                )
            ],
        ]
    )


def empty_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Aggiorna coda",
                    callback_data=(
                        "autopost:queue"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Configurazione",
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
# MOSTRA CANDIDATO
# =========================================================


async def show_pending(
    query: CallbackQuery,
    state: FSMContext,
    index: int,
) -> None:
    settings = get_settings()

    channel_id = await get_channel_id(
        state
    )

    if channel_id is None:
        await query.answer(
            "Seleziona prima un canale.",
            show_alert=True,
        )

        return

    rows = (
        await list_owner_pending_candidates(
            owner_telegram_user_id=(
                settings.admin_user_id
            ),
            channel_id=channel_id,
            limit=100,
        )
    )

    if not rows:
        await state.update_data(
            autopost_queue_index=0
        )

        if query.message is not None:
            await query.message.edit_text(
                "📥 <b>Coda Autopost</b>"
                "\n\n"
                "✅ Nessun candidato "
                "in attesa."
                "\n\n"
                "Quando lo scheduler "
                "troverà una nuova offerta "
                "valida, comparirà qui.",
                reply_markup=(
                    empty_keyboard()
                ),
            )

        await query.answer()

        return

    safe_index = (
        index % len(rows)
    )

    candidate, channel = (
        rows[safe_index]
    )

    await state.update_data(
        autopost_queue_index=(
            safe_index
        )
    )

    if query.message is not None:
        await query.message.edit_text(
            pending_text(
                candidate,
                channel,
                safe_index + 1,
                len(rows),
            ),
            reply_markup=(
                pending_keyboard(
                    candidate.id
                )
            ),
        )

    await query.answer()


# =========================================================
# APRI CODA
# =========================================================


@router.callback_query(
    F.data == "autopost:queue"
)
async def queue_open(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await show_pending(
        query,
        state,
        0,
    )


# =========================================================
# PROSSIMO
# =========================================================


@router.callback_query(
    F.data == "autopost:queue_next"
)
async def queue_next(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    data = await state.get_data()

    current = int(
        data.get(
            "autopost_queue_index",
            0,
        )
    )

    await show_pending(
        query,
        state,
        current + 1,
    )


# =========================================================
# APPROVA
# =========================================================


@router.callback_query(
    F.data.startswith(
        "autopost:queue_approve:"
    )
)
async def queue_approve(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    candidate_id = int(
        query.data.split(":")[-1]
    )

    approved = (
        await approve_candidate(
            settings.admin_user_id,
            candidate_id,
        )
    )

    if approved is None:
        await query.answer(
            "Candidato già gestito.",
            show_alert=True,
        )

        return

    delivery = (
        await get_owner_candidate(
            settings.admin_user_id,
            candidate_id,
        )
    )

    if delivery is None:
        await query.answer(
            "Candidato non trovato.",
            show_alert=True,
        )

        return

    candidate, channel = (
        delivery
    )

    if query.message is not None:
        await query.message.edit_text(
            approved_text(
                candidate,
                channel,
            ),
            reply_markup=(
                approved_keyboard(
                    candidate.id
                )
            ),
        )

    await query.answer(
        "Candidato approvato."
    )


# =========================================================
# SCARTA
# =========================================================


@router.callback_query(
    F.data.startswith(
        "autopost:queue_reject:"
    )
)
async def queue_reject(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    candidate_id = int(
        query.data.split(":")[-1]
    )

    rejected = (
        await reject_candidate(
            settings.admin_user_id,
            candidate_id,
        )
    )

    if rejected is None:
        await query.answer(
            "Candidato già gestito.",
            show_alert=True,
        )

        return

    data = await state.get_data()

    current = int(
        data.get(
            "autopost_queue_index",
            0,
        )
    )

    await query.answer(
        "Candidato scartato."
    )

    await show_pending(
        query,
        state,
        current,
    )


# =========================================================
# TORNA PENDING
# =========================================================


@router.callback_query(
    F.data.startswith(
        "autopost:queue_restore:"
    )
)
async def queue_restore(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    candidate_id = int(
        query.data.split(":")[-1]
    )

    restored = (
        await restore_candidate_pending(
            settings.admin_user_id,
            candidate_id,
        )
    )

    if restored is None:
        await query.answer(
            "Impossibile ripristinare.",
            show_alert=True,
        )

        return

    await query.answer(
        "Candidato riportato in attesa."
    )

    await show_pending(
        query,
        state,
        0,
    )


# =========================================================
# PUBBLICA - 10E
# =========================================================


@router.callback_query(
    F.data.startswith(
        "autopost:queue_publish:"
    )
)
async def queue_publish(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    candidate_id = int(
        query.data.split(":")[-1]
    )

    delivery = (
        await get_owner_candidate(
            settings.admin_user_id,
            candidate_id,
        )
    )

    if delivery is None:
        await query.answer(
            "Candidato non trovato.",
            show_alert=True,
        )

        return

    candidate, channel = (
        delivery
    )

    if (
        candidate.status
        != STATUS_APPROVED
    ):
        await query.answer(
            "Il candidato non è "
            "in stato APPROVED.",
            show_alert=True,
        )

        return

    try:
        result = (
            await publish_approved_candidate(
                bot=bot,
                owner_telegram_user_id=(
                    settings.admin_user_id
                ),
                candidate_id=(
                    candidate_id
                ),
            )
        )

    except Exception as exc:
        await query.answer(
            (
                "Pubblicazione fallita: "
                f"{str(exc)[:150]}"
            ),
            show_alert=True,
        )

        return

    if query.message is not None:
        await query.message.edit_text(
            "✅ <b>Offerta pubblicata!</b>"
            "\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n"
            f"👀 {escape(candidate.title)}"
            "\n"
            f"🔢 ASIN: "
            f"<code>"
            f"{escape(candidate.asin)}"
            f"</code>"
            "\n\n"
            f"📨 Telegram message ID: "
            f"<code>"
            f"{result.telegram_message_id}"
            f"</code>"
            "\n\n"
            "♻️ Pubblicazione registrata "
            "anche nello storico "
            "anti-duplicati.",
            reply_markup=(
                InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text=(
                                    "📥 Prossimo "
                                    "candidato"
                                ),
                                callback_data=(
                                    "autopost:queue"
                                ),
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text=(
                                    "⬅️ "
                                    "Configurazione"
                                ),
                                callback_data=(
                                    "autopost:"
                                    "config_back"
                                ),
                            )
                        ],
                    ]
                )
            ),
        )

    await query.answer(
        "Pubblicazione completata."
    )
