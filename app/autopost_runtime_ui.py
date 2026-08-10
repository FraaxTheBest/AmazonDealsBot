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

from app.autopost_runtime_store import (
    ChannelAutopostRuntimeConfig,
    get_or_create_runtime_config,
    reset_runtime_config,
    set_autopost_enabled,
    set_runtime_value,
)
from app.autopost_scheduler import (
    refresh_autopost_channel,
)
from app.autopost_store import (
    get_or_create_autopost_config,
)
from app.config import get_settings
from app.database import get_channel


router = Router(
    name="autopost_runtime"
)


class RuntimeConfigStates(
    StatesGroup
):
    waiting_value = State()


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


def minutes_text(
    minutes: int,
) -> str:
    if minutes < 60:
        if minutes == 1:
            return "1 minuto"

        return (
            f"{minutes} minuti"
        )

    if minutes % 60 == 0:
        hours = minutes // 60

        if hours == 1:
            return "1 ora"

        return (
            f"{hours} ore"
        )

    hours = minutes // 60

    remaining = minutes % 60

    return (
        f"{hours}h {remaining}m"
    )


def runtime_summary(
    enabled: bool,
    runtime: ChannelAutopostRuntimeConfig,
) -> str:
    status = (
        "✅ ON"
        if enabled
        else "❌ OFF"
    )

    return (
        f"🤖 Autoposting: "
        f"<b>{status}</b>"
        "\n"
        f"🔎 Scansione: "
        f"<b>"
        f"{minutes_text(
            runtime
            .scan_interval_minutes
        )}"
        f"</b>"
        "\n"
        f"📤 Intervallo pubblicazione: "
        f"<b>"
        f"{minutes_text(
            runtime
            .publish_interval_minutes
        )}"
        f"</b>"
        "\n"
        f"📦 Max candidati/scansione: "
        f"<b>"
        f"{runtime
        .max_candidates_per_scan}"
        f"</b>"
    )


def field_label(
    field: str,
) -> str:
    labels = {
        "scan_interval_minutes":
            "🔎 Intervallo scansione",

        "publish_interval_minutes":
            "📤 Intervallo pubblicazione",

        "max_candidates_per_scan":
            "📦 Max candidati per scansione",
    }

    return labels.get(
        field,
        field,
    )


def field_example(
    field: str,
) -> str:
    examples = {
        "scan_interval_minutes":
            "15",

        "publish_interval_minutes":
            "45",

        "max_candidates_per_scan":
            "3",
    }

    return examples.get(
        field,
        "1",
    )


def field_limits_text(
    field: str,
) -> str:
    if (
        field
        == "max_candidates_per_scan"
    ):
        return (
            "Valori ammessi: "
            "<b>1–50</b>."
        )

    return (
        "Valori ammessi: "
        "<b>1–1440 minuti</b>."
    )


# =========================================================
# KEYBOARDS
# =========================================================


def runtime_keyboard(
    enabled: bool,
) -> InlineKeyboardMarkup:
    toggle_text = (
        "🔴 Disattiva Autoposting"
        if enabled
        else "🟢 Attiva Autoposting"
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data=(
                        "autopost:"
                        "runtime_toggle"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🔎 Intervallo scansione"
                    ),
                    callback_data=(
                        "autopost:runtime_field:"
                        "scan_interval_minutes"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "📤 Intervallo "
                        "pubblicazione"
                    ),
                    callback_data=(
                        "autopost:runtime_field:"
                        "publish_interval_minutes"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "📦 Max candidati "
                        "per scansione"
                    ),
                    callback_data=(
                        "autopost:runtime_field:"
                        "max_candidates_per_scan"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "♻️ Ripristina default"
                    ),
                    callback_data=(
                        "autopost:runtime_reset"
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


def runtime_input_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "⬅️ Impostazioni "
                        "Autopost"
                    ),
                    callback_data=(
                        "autopost:runtime"
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


# =========================================================
# MENU
# =========================================================


@router.callback_query(
    F.data == "autopost:runtime"
)
async def runtime_menu(
    query: CallbackQuery,
    state: FSMContext,
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

    autopost_config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    runtime = (
        await get_or_create_runtime_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    await state.set_state(
        None
    )

    if query.message is not None:
        await query.message.edit_text(
            "⚡ <b>Configurazione "
            "Autoposting</b>"
            "\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            f"{runtime_summary(
                bool(
                    autopost_config
                    .is_enabled
                ),
                runtime,
            )}"
            "\n\n"
            "⚙️ Le modifiche vengono "
            "salvate nel database."
            "\n\n"
            "🔄 Se cambi ON/OFF o "
            "l'intervallo di scansione, "
            "lo Scheduler Autoposting "
            "si aggiorna automaticamente."
            "\n\n"
            "⚠️ Fase 10B: vengono "
            "eseguite scansioni reali "
            "della pipeline DEMO, "
            "ma non viene ancora "
            "pubblicato nessun post.",
            reply_markup=(
                runtime_keyboard(
                    bool(
                        autopost_config
                        .is_enabled
                    )
                )
            ),
        )

    await query.answer()


# =========================================================
# ON / OFF
# =========================================================


@router.callback_query(
    F.data
    == "autopost:runtime_toggle"
)
async def runtime_toggle(
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

    current = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    updated = (
        await set_autopost_enabled(
            settings.admin_user_id,
            channel_id,
            not bool(
                current.is_enabled
            ),
        )
    )

    # =====================================================
    # FASE 10B
    #
    # ON  → crea/aggiorna job
    # OFF → rimuove job
    # =====================================================

    await refresh_autopost_channel(
        settings.admin_user_id,
        channel_id,
    )

    runtime = (
        await get_or_create_runtime_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    enabled = bool(
        updated.is_enabled
    )

    if query.message is not None:
        await query.message.edit_text(
            "⚡ <b>Configurazione "
            "Autoposting</b>"
            "\n\n"
            f"{runtime_summary(
                enabled,
                runtime,
            )}"
            "\n\n"
            "✅ Configurazione salvata."
            "\n\n"
            (
                "🔄 Scheduler Autoposting "
                "<b>ATTIVO</b>."
                if enabled
                else
                "⏸ Scheduler Autoposting "
                "<b>DISATTIVATO</b>."
            ),
            reply_markup=(
                runtime_keyboard(
                    enabled
                )
            ),
        )

    await query.answer(
        (
            "Autoposting ON."
            if enabled
            else "Autoposting OFF."
        )
    )


# =========================================================
# MODIFICA CAMPO
# =========================================================


@router.callback_query(
    F.data.startswith(
        "autopost:runtime_field:"
    )
)
async def runtime_edit_field(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    field = (
        query.data.split(":")[-1]
    )

    allowed = {
        "scan_interval_minutes",
        "publish_interval_minutes",
        "max_candidates_per_scan",
    }

    if field not in allowed:
        await query.answer(
            "Impostazione non valida.",
            show_alert=True,
        )

        return

    await state.update_data(
        autopost_runtime_field=field
    )

    await state.set_state(
        RuntimeConfigStates
        .waiting_value
    )

    if query.message is not None:
        await query.message.edit_text(
            f"{field_label(field)}"
            "\n\n"
            "Invia il nuovo valore "
            "come numero intero."
            "\n\n"
            f"{field_limits_text(field)}"
            "\n\n"
            "Esempio:\n"
            f"<code>"
            f"{field_example(field)}"
            f"</code>",
            reply_markup=(
                runtime_input_keyboard()
            ),
        )

    await query.answer()


# =========================================================
# RICEZIONE VALORE
# =========================================================


@router.message(
    RuntimeConfigStates
    .waiting_value
)
async def runtime_receive_value(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.text:
        await message.answer(
            "❌ Invia un numero intero."
        )

        return

    settings = get_settings()

    data = await state.get_data()

    channel_id = data.get(
        "autopost_channel_id"
    )

    field = data.get(
        "autopost_runtime_field"
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
        value = int(
            message.text.strip()
        )

        runtime = (
            await set_runtime_value(
                settings.admin_user_id,
                int(channel_id),
                str(field),
                value,
            )
        )

        # ================================================
        # FASE 10B
        #
        # Se cambia l'intervallo
        # scansione, ricreiamo
        # immediatamente il job.
        # ================================================

        if (
            str(field)
            == "scan_interval_minutes"
        ):
            await refresh_autopost_channel(
                settings.admin_user_id,
                int(channel_id),
            )

    except ValueError as exc:
        await message.answer(
            "❌ Valore non valido."
            "\n\n"
            f"{escape(str(exc))}",
            reply_markup=(
                runtime_input_keyboard()
            ),
        )

        return

    autopost_config = (
        await get_or_create_autopost_config(
            settings.admin_user_id,
            int(channel_id),
        )
    )

    await state.set_state(
        None
    )

    await state.update_data(
        autopost_runtime_field=None
    )

    await message.answer(
        "✅ <b>Impostazione "
        "aggiornata</b>"
        "\n\n"
        f"{runtime_summary(
            bool(
                autopost_config
                .is_enabled
            ),
            runtime,
        )}",
        reply_markup=(
            runtime_keyboard(
                bool(
                    autopost_config
                    .is_enabled
                )
            )
        ),
    )


# =========================================================
# RESET
# =========================================================


@router.callback_query(
    F.data
    == "autopost:runtime_reset"
)
async def runtime_reset(
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

    runtime = (
        await reset_runtime_config(
            settings.admin_user_id,
            channel_id,
        )
    )

    # =====================================================
    # RESET = Autopost OFF
    # quindi rimuoviamo anche
    # il job dallo scheduler.
    # =====================================================

    await refresh_autopost_channel(
        settings.admin_user_id,
        channel_id,
    )

    if query.message is not None:
        await query.message.edit_text(
            "♻️ <b>Configurazione "
            "ripristinata</b>"
            "\n\n"
            f"{runtime_summary(
                False,
                runtime,
            )}"
            "\n\n"
            "⏸ Scheduler Autoposting "
            "<b>DISATTIVATO</b>.",
            reply_markup=(
                runtime_keyboard(
                    False
                )
            ),
        )

    await query.answer(
        "Default ripristinati."
    )
