from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from app.autopost_advanced_store import (
    BLACKLIST_BRAND,
    BLACKLIST_SELLER,
    MODE_APPROVAL,
    MODE_AUTOMATIC,
    PUBLISH_INTERVAL,
    PUBLISH_SLOTS,
    RANK_BEST,
    RANK_DISCOUNT,
    RANK_RECENT,
    add_blacklist_entry,
    event_status,
    get_or_create_advanced_config,
    get_publish_slots,
    list_blacklist_entries,
    remove_blacklist_entry,
    set_advanced_value,
    set_publish_slots,
)
from app.autopost_auto_service import live_ranking_snapshot
from app.autopost_runtime_store import get_or_create_runtime_config
from app.autopost_scheduler import refresh_autopost_channel
from app.config import get_settings
from app.database import get_channel


router = Router(name="autopost_advanced")


class AdvancedStates(StatesGroup):
    waiting_numeric = State()
    waiting_slots = State()
    waiting_event_name = State()
    waiting_event_datetime = State()
    waiting_blacklist = State()


NUMERIC_FIELDS = {
    "priority_lightning",
    "priority_coupon",
    "priority_lowest",
    "priority_warehouse",
    "priority_normal",
    "max_posts_per_day",
    "max_category_per_day",
    "max_brand_per_day",
    "event_scan_interval_minutes",
    "event_publish_interval_minutes",
    "event_max_posts_per_day",
    "retry_limit",
    "stale_publish_minutes",
}


FIELD_LABELS = {
    "priority_lightning": "⚡ Priorità Offerta Lampo",
    "priority_coupon": "🏷 Priorità Coupon",
    "priority_lowest": "📉 Priorità Prezzo minimo",
    "priority_warehouse": "📦 Priorità Warehouse",
    "priority_normal": "💰 Priorità Normale",
    "max_posts_per_day": "📤 Max post/giorno",
    "max_category_per_day": "🗂 Max categoria/giorno",
    "max_brand_per_day": "🏷 Max brand/giorno",
    "event_scan_interval_minutes": "🔎 Scansione evento",
    "event_publish_interval_minutes": "📤 Pubblicazione evento",
    "event_max_posts_per_day": "🔥 Max post evento/giorno",
    "retry_limit": "🔁 Tentativi pubblicazione",
    "stale_publish_minutes": "🛡 Timeout publishing",
}


async def _channel_id(state: FSMContext) -> int | None:
    data = await state.get_data()
    value = data.get("autopost_channel_id")
    return int(value) if value is not None else None


def _mode_text(value: str) -> str:
    return (
        "✅ Con approvazione"
        if value == MODE_APPROVAL
        else "🤖 Automatico"
    )


def _ranking_text(value: str) -> str:
    return {
        RANK_BEST: "🧠 Migliore offerta",
        RANK_DISCOUNT: "📉 Sconto più alto",
        RANK_RECENT: "🆕 Più recente",
    }.get(value, value)


def _strategy_text(value: str) -> str:
    return (
        "⏱ Ogni X minuti"
        if value == PUBLISH_INTERVAL
        else "🕐 Orari precisi"
    )


def _advanced_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Modalità",
                    callback_data="autopost:adv_mode",
                ),
                InlineKeyboardButton(
                    text="🔍 Classifica live",
                    callback_data="autopost:adv_live",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧠 Ranking",
                    callback_data="autopost:adv_ranking",
                ),
                InlineKeyboardButton(
                    text="⭐ Priorità",
                    callback_data="autopost:adv_priority",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Rotazione e limiti",
                    callback_data="autopost:adv_rules",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🕐 Orari",
                    callback_data="autopost:adv_schedule",
                ),
                InlineKeyboardButton(
                    text="🔥 Evento",
                    callback_data="autopost:adv_event",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Blacklist",
                    callback_data="autopost:adv_blacklist",
                ),
                InlineKeyboardButton(
                    text="🛡 Affidabilità",
                    callback_data="autopost:adv_reliability",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Configurazione",
                    callback_data="autopost:config_back",
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="menu:home",
                ),
            ],
        ]
    )


async def _show_main(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        await query.answer("Seleziona prima un canale.", show_alert=True)
        return

    channel = await get_channel(channel_id, settings.admin_user_id)
    if channel is None:
        await query.answer("Canale non trovato.", show_alert=True)
        return

    advanced = await get_or_create_advanced_config(
        settings.admin_user_id,
        channel_id,
    )
    runtime = await get_or_create_runtime_config(
        settings.admin_user_id,
        channel_id,
    )
    event = event_status(advanced)
    slots = get_publish_slots(advanced)

    event_text = (
        f"🔥 {escape(event.name or 'Evento')} ATTIVO"
        if event.active
        else (
            "🟡 Configurato, non attivo ora"
            if advanced.event_enabled
            else "⚪ Disattivato"
        )
    )

    text = (
        "🧠 <b>Autoposting avanzato</b>"
        "\n\n"
        f"📢 <b>{escape(channel.title)}</b>"
        "\n\n"
        f"Modalità: <b>{_mode_text(advanced.mode)}</b>"
        "\n"
        f"Ranking: <b>{_ranking_text(advanced.ranking_mode)}</b>"
        "\n"
        f"Pubblicazione: <b>{_strategy_text(advanced.publish_strategy)}</b>"
        "\n"
        f"🔎 Scan base: <b>{runtime.scan_interval_minutes} min</b>"
        "\n"
        f"📤 Intervallo base: <b>{runtime.publish_interval_minutes} min</b>"
        "\n"
        f"🕐 Slot: <b>{', '.join(slots) if slots else 'nessuno'}</b>"
        "\n"
        f"Evento: <b>{event_text}</b>"
        "\n\n"
        "Un solo Autoposting: in modalità approvazione riempie la coda; "
        "in modalità automatica pubblica rispettando ranking, limiti, "
        "rotazione, orari e anti-duplicati."
    )

    if query.message is not None:
        await query.message.edit_text(text, reply_markup=_advanced_keyboard())
    await query.answer()


@router.callback_query(F.data == "autopost:advanced")
async def advanced_main(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(None)
    await _show_main(query, state)


@router.callback_query(F.data == "autopost:adv_mode")
async def mode_menu(query: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Con approvazione",
                    callback_data="autopost:adv_mode_set:approval",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Automatico",
                    callback_data="autopost:adv_mode_set:automatic",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Avanzate",
                    callback_data="autopost:advanced",
                )
            ],
        ]
    )
    if query.message is not None:
        await query.message.edit_text(
            "🔁 <b>Modalità Autoposting</b>\n\n"
            "✅ Con approvazione: trova → coda → decidi tu.\n\n"
            "🤖 Automatico: trova → classifica → pubblica da solo "
            "quando arriva l'intervallo/slot.",
            reply_markup=keyboard,
        )
    await query.answer()


@router.callback_query(F.data.startswith("autopost:adv_mode_set:"))
async def mode_set(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None or query.data is None:
        return
    mode = query.data.rsplit(":", 1)[-1]
    await set_advanced_value(settings.admin_user_id, channel_id, "mode", mode)
    await refresh_autopost_channel(settings.admin_user_id, channel_id)
    await _show_main(query, state)


@router.callback_query(F.data == "autopost:adv_ranking")
async def ranking_menu(query: CallbackQuery) -> None:
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Migliore offerta", callback_data="autopost:adv_rank_set:best")],
            [InlineKeyboardButton(text="📉 Sconto più alto", callback_data="autopost:adv_rank_set:discount")],
            [InlineKeyboardButton(text="🆕 Più recente", callback_data="autopost:adv_rank_set:recent")],
            [InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")],
        ]
    )
    if query.message is not None:
        await query.message.edit_text(
            "🧠 <b>Ranking</b>\n\n"
            "Migliore offerta combina Deal Engine + priorità.\n"
            "Sconto mette in evidenza la percentuale.\n"
            "Più recente usa il timestamp del provider quando disponibile.",
            reply_markup=keyboard,
        )
    await query.answer()


@router.callback_query(F.data.startswith("autopost:adv_rank_set:"))
async def ranking_set(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None or query.data is None:
        return
    value = query.data.rsplit(":", 1)[-1]
    await set_advanced_value(
        settings.admin_user_id,
        channel_id,
        "ranking_mode",
        value,
    )
    await _show_main(query, state)


@router.callback_query(F.data == "autopost:adv_priority")
async def priority_menu(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return
    config = await get_or_create_advanced_config(settings.admin_user_id, channel_id)

    rows = []
    for field in (
        "priority_lightning",
        "priority_coupon",
        "priority_lowest",
        "priority_warehouse",
        "priority_normal",
    ):
        rows.append([
            InlineKeyboardButton(
                text=f"{FIELD_LABELS[field]}: {getattr(config, field):+d}",
                callback_data=f"autopost:adv_num:{field}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")])

    if query.message is not None:
        await query.message.edit_text(
            "⭐ <b>Priorità offerte</b>\n\n"
            "Il valore viene sommato allo score del Deal Engine. "
            "Non sostituisce i controlli qualità.\n\n"
            "Range: -100 … +100.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await query.answer()


@router.callback_query(F.data == "autopost:adv_rules")
async def rules_menu(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return
    config = await get_or_create_advanced_config(settings.admin_user_id, channel_id)

    cat = "✅" if config.alternate_categories else "❌"
    brand = "✅" if config.alternate_brands else "❌"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=f"{cat} Alterna categorie", callback_data="autopost:adv_toggle:alternate_categories"),
                InlineKeyboardButton(text=f"{brand} Alterna brand", callback_data="autopost:adv_toggle:alternate_brands"),
            ],
            [InlineKeyboardButton(text=f"📤 Max post/giorno: {config.max_posts_per_day or 'OFF'}", callback_data="autopost:adv_num:max_posts_per_day")],
            [InlineKeyboardButton(text=f"🗂 Max categoria/giorno: {config.max_category_per_day or 'OFF'}", callback_data="autopost:adv_num:max_category_per_day")],
            [InlineKeyboardButton(text=f"🏷 Max brand/giorno: {config.max_brand_per_day or 'OFF'}", callback_data="autopost:adv_num:max_brand_per_day")],
            [InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")],
        ]
    )
    if query.message is not None:
        await query.message.edit_text(
            "🔁 <b>Rotazione e limiti</b>\n\n"
            "0 = nessun limite. Se non esiste una valida alternativa, "
            "la rotazione usa un fallback e non blocca il canale.",
            reply_markup=keyboard,
        )
    await query.answer()


@router.callback_query(F.data.startswith("autopost:adv_toggle:"))
async def toggle_option(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None or query.data is None:
        return
    field = query.data.rsplit(":", 1)[-1]
    if field not in {"alternate_categories", "alternate_brands"}:
        return
    config = await get_or_create_advanced_config(settings.admin_user_id, channel_id)
    await set_advanced_value(
        settings.admin_user_id,
        channel_id,
        field,
        not bool(getattr(config, field)),
    )
    await rules_menu(query, state)


@router.callback_query(F.data.startswith("autopost:adv_num:"))
async def numeric_prompt(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None:
        return
    field = query.data.rsplit(":", 1)[-1]
    if field not in NUMERIC_FIELDS:
        await query.answer("Campo non valido.", show_alert=True)
        return
    await state.update_data(autopost_adv_field=field)
    await state.set_state(AdvancedStates.waiting_numeric)
    if query.message is not None:
        await query.message.edit_text(
            f"{FIELD_LABELS[field]}\n\n"
            "Invia un numero intero. Per i limiti giornalieri, 0 = OFF."
        )
    await query.answer()


@router.message(AdvancedStates.waiting_numeric)
async def numeric_receive(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    channel_id = data.get("autopost_channel_id")
    field = data.get("autopost_adv_field")
    if channel_id is None or field not in NUMERIC_FIELDS or not message.text:
        await state.set_state(None)
        await message.answer("❌ Sessione scaduta.")
        return
    try:
        value = int(message.text.strip())
        await set_advanced_value(
            settings.admin_user_id,
            int(channel_id),
            str(field),
            value,
        )
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    await state.set_state(None)
    await state.update_data(autopost_adv_field=None)
    if field in {
        "event_scan_interval_minutes",
        "event_publish_interval_minutes",
    }:
        await refresh_autopost_channel(settings.admin_user_id, int(channel_id))
    await message.answer(
        "✅ Impostazione salvata.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="🧠 Torna alle avanzate", callback_data="autopost:advanced")
            ]]
        ),
    )


@router.callback_query(F.data == "autopost:adv_schedule")
async def schedule_menu(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return
    config = await get_or_create_advanced_config(settings.admin_user_id, channel_id)
    runtime = await get_or_create_runtime_config(settings.admin_user_id, channel_id)
    slots = get_publish_slots(config)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏱ Ogni X minuti", callback_data="autopost:adv_strategy:interval")],
            [InlineKeyboardButton(text="🕐 Orari precisi", callback_data="autopost:adv_strategy:slots")],
            [InlineKeyboardButton(text="✏️ Imposta slot", callback_data="autopost:adv_slots_edit")],
            [InlineKeyboardButton(text="⚡ Modifica intervalli base", callback_data="autopost:runtime")],
            [InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")],
        ]
    )
    if query.message is not None:
        await query.message.edit_text(
            "🕐 <b>Orari pubblicazione</b>\n\n"
            f"Strategia: <b>{_strategy_text(config.publish_strategy)}</b>\n"
            f"Intervallo: <b>{runtime.publish_interval_minutes} min</b>\n"
            f"Slot: <b>{', '.join(slots) if slots else 'nessuno'}</b>\n\n"
            "Gli slot sono usati solo in modalità Automatica e fuori da un Evento attivo.",
            reply_markup=keyboard,
        )
    await query.answer()


@router.callback_query(F.data.startswith("autopost:adv_strategy:"))
async def strategy_set(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None or query.data is None:
        return
    value = query.data.rsplit(":", 1)[-1]
    await set_advanced_value(
        settings.admin_user_id,
        channel_id,
        "publish_strategy",
        value,
    )
    await refresh_autopost_channel(settings.admin_user_id, channel_id)
    await schedule_menu(query, state)


@router.callback_query(F.data == "autopost:adv_slots_edit")
async def slots_prompt(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdvancedStates.waiting_slots)
    if query.message is not None:
        await query.message.edit_text(
            "🕐 <b>Imposta slot</b>\n\n"
            "Invia gli orari separati da virgola.\n"
            "Esempio: <code>09:00,11:30,14:00,19:30</code>\n\n"
            "Invia <code>off</code> per svuotare gli slot."
        )
    await query.answer()


@router.message(AdvancedStates.waiting_slots)
async def slots_receive(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None or not message.text:
        await state.set_state(None)
        return
    raw = message.text.strip()
    slots = [] if raw.lower() == "off" else [item.strip() for item in raw.split(",") if item.strip()]
    try:
        await set_publish_slots(settings.admin_user_id, channel_id, slots)
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    await state.set_state(None)
    await refresh_autopost_channel(settings.admin_user_id, channel_id)
    await message.answer(
        "✅ Slot salvati.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🕐 Torna agli orari", callback_data="autopost:adv_schedule")
        ]]),
    )


@router.callback_query(F.data == "autopost:adv_event")
async def event_menu(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return
    config = await get_or_create_advanced_config(settings.admin_user_id, channel_id)
    event = event_status(config)
    start = config.event_start_at.isoformat(sep=" ", timespec="minutes") if config.event_start_at else "N/D"
    end = config.event_end_at.isoformat(sep=" ", timespec="minutes") if config.event_end_at else "N/D"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=("🔴 Disattiva Evento" if config.event_enabled else "🟢 Attiva Evento"), callback_data="autopost:adv_event_toggle")],
            [InlineKeyboardButton(text="✏️ Nome evento", callback_data="autopost:adv_event_name")],
            [InlineKeyboardButton(text="▶️ Inizio", callback_data="autopost:adv_event_dt:event_start_at")],
            [InlineKeyboardButton(text="⏹ Fine", callback_data="autopost:adv_event_dt:event_end_at")],
            [InlineKeyboardButton(text=f"🔎 Scan evento: {config.event_scan_interval_minutes}m", callback_data="autopost:adv_num:event_scan_interval_minutes")],
            [InlineKeyboardButton(text=f"📤 Publish evento: {config.event_publish_interval_minutes}m", callback_data="autopost:adv_num:event_publish_interval_minutes")],
            [InlineKeyboardButton(text=f"🔥 Max/giorno: {config.event_max_posts_per_day or 'OFF'}", callback_data="autopost:adv_num:event_max_posts_per_day")],
            [InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")],
        ]
    )
    if query.message is not None:
        await query.message.edit_text(
            "🔥 <b>Modalità Evento</b>\n\n"
            f"Stato: <b>{'ATTIVO ORA' if event.active else ('ABILITATO' if config.event_enabled else 'OFF')}</b>\n"
            f"Nome: <b>{escape(config.event_name or 'Evento')}</b>\n"
            f"Inizio UTC salvato: <code>{escape(start)}</code>\n"
            f"Fine UTC salvata: <code>{escape(end)}</code>\n\n"
            "Durante l'evento vengono usati gli intervalli evento; alla fine il bot torna automaticamente alla configurazione normale.",
            reply_markup=keyboard,
        )
    await query.answer()


@router.callback_query(F.data == "autopost:adv_event_toggle")
async def event_toggle(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return
    config = await get_or_create_advanced_config(settings.admin_user_id, channel_id)
    await set_advanced_value(settings.admin_user_id, channel_id, "event_enabled", not config.event_enabled)
    await refresh_autopost_channel(settings.admin_user_id, channel_id)
    await event_menu(query, state)


@router.callback_query(F.data == "autopost:adv_event_name")
async def event_name_prompt(query: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdvancedStates.waiting_event_name)
    if query.message is not None:
        await query.message.edit_text("🔥 Invia il nome dell'evento. Esempio: Prime Day")
    await query.answer()


@router.message(AdvancedStates.waiting_event_name)
async def event_name_receive(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None or not message.text:
        await state.set_state(None)
        return
    try:
        await set_advanced_value(settings.admin_user_id, channel_id, "event_name", message.text)
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    await state.set_state(None)
    await message.answer("✅ Nome evento salvato.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔥 Torna all'evento", callback_data="autopost:adv_event")
    ]]))


@router.callback_query(F.data.startswith("autopost:adv_event_dt:"))
async def event_datetime_prompt(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None:
        return
    field = query.data.rsplit(":", 1)[-1]
    if field not in {"event_start_at", "event_end_at"}:
        return
    await state.update_data(autopost_adv_event_dt_field=field)
    await state.set_state(AdvancedStates.waiting_event_datetime)
    if query.message is not None:
        await query.message.edit_text(
            "🗓 Invia data e ora locali nel formato:\n"
            "<code>2026-10-08 09:00</code>\n\n"
            "Verrà usato il fuso orario APP_TIMEZONE."
        )
    await query.answer()


@router.message(AdvancedStates.waiting_event_datetime)
async def event_datetime_receive(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    channel_id = data.get("autopost_channel_id")
    field = data.get("autopost_adv_event_dt_field")
    if channel_id is None or field not in {"event_start_at", "event_end_at"} or not message.text:
        await state.set_state(None)
        return
    try:
        local_naive = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        local_dt = local_naive.replace(tzinfo=ZoneInfo(settings.app_timezone))
        await set_advanced_value(settings.admin_user_id, int(channel_id), str(field), local_dt)
    except (ValueError, KeyError) as exc:
        await message.answer(f"❌ Data non valida: {escape(str(exc))}")
        return
    await state.set_state(None)
    await state.update_data(autopost_adv_event_dt_field=None)
    await refresh_autopost_channel(settings.admin_user_id, int(channel_id))
    await message.answer("✅ Data evento salvata.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔥 Torna all'evento", callback_data="autopost:adv_event")
    ]]))


@router.callback_query(F.data == "autopost:adv_blacklist")
async def blacklist_menu(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return
    entries = await list_blacklist_entries(settings.admin_user_id, channel_id)
    lines = ["🚫 <b>Blacklist</b>", ""]
    if not entries:
        lines.append("Nessun brand o venditore escluso.")
    else:
        for entry in entries[:20]:
            icon = "🏷" if entry.kind == BLACKLIST_BRAND else "🏪"
            lines.append(f"{icon} #{entry.id} {escape(entry.value_display)}")

    rows = [
        [
            InlineKeyboardButton(text="➕ Brand", callback_data="autopost:adv_black_add:brand"),
            InlineKeyboardButton(text="➕ Venditore", callback_data="autopost:adv_black_add:seller"),
        ]
    ]
    for entry in entries[:12]:
        rows.append([
            InlineKeyboardButton(
                text=f"🗑 #{entry.id} {entry.value_display[:22]}",
                callback_data=f"autopost:adv_black_del:{entry.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")])

    if query.message is not None:
        await query.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
    await query.answer()


@router.callback_query(F.data.startswith("autopost:adv_black_add:"))
async def blacklist_add_prompt(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None:
        return
    kind = query.data.rsplit(":", 1)[-1]
    if kind not in {BLACKLIST_BRAND, BLACKLIST_SELLER}:
        return
    await state.update_data(autopost_adv_black_kind=kind)
    await state.set_state(AdvancedStates.waiting_blacklist)
    if query.message is not None:
        await query.message.edit_text(
            "🚫 Invia il nome esatto del brand o venditore da escludere."
        )
    await query.answer()


@router.message(AdvancedStates.waiting_blacklist)
async def blacklist_add_receive(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    channel_id = data.get("autopost_channel_id")
    kind = data.get("autopost_adv_black_kind")
    if channel_id is None or kind not in {BLACKLIST_BRAND, BLACKLIST_SELLER} or not message.text:
        await state.set_state(None)
        return
    try:
        await add_blacklist_entry(settings.admin_user_id, int(channel_id), str(kind), message.text)
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}")
        return
    await state.set_state(None)
    await state.update_data(autopost_adv_black_kind=None)
    await message.answer("✅ Aggiunto alla blacklist.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚫 Torna alla blacklist", callback_data="autopost:adv_blacklist")
    ]]))


@router.callback_query(F.data.startswith("autopost:adv_black_del:"))
async def blacklist_delete(query: CallbackQuery, state: FSMContext) -> None:
    if query.data is None:
        return
    settings = get_settings()
    entry_id = int(query.data.rsplit(":", 1)[-1])
    await remove_blacklist_entry(settings.admin_user_id, entry_id)
    await blacklist_menu(query, state)


@router.callback_query(F.data == "autopost:adv_reliability")
async def reliability_menu(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return
    config = await get_or_create_advanced_config(settings.admin_user_id, channel_id)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔁 Retry: {config.retry_limit}", callback_data="autopost:adv_num:retry_limit")],
            [InlineKeyboardButton(text=f"🛡 Timeout publishing: {config.stale_publish_minutes}m", callback_data="autopost:adv_num:stale_publish_minutes")],
            [InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")],
        ]
    )
    if query.message is not None:
        await query.message.edit_text(
            "🛡 <b>Affidabilità</b>\n\n"
            "Il claim DB impedisce il doppio click. Il publisher automatico usa un lock per canale. "
            "I fallimenti vengono ritentati fino al limite; gli stati publishing rimasti bloccati dopo un crash "
            "vengono marcati FAILED in modo conservativo per evitare doppie pubblicazioni.",
            reply_markup=keyboard,
        )
    await query.answer()


@router.callback_query(F.data == "autopost:adv_live")
async def live_ranking(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    channel_id = await _channel_id(state)
    if channel_id is None:
        return

    snapshot = await live_ranking_snapshot(settings.admin_user_id, channel_id)
    lines = [
        "🔍 <b>Classifica live</b>",
        "",
        "Se il bot dovesse scegliere adesso, questo sarebbe l'ordine.",
        "",
    ]

    if not snapshot.ranking.ranked:
        lines.append("Nessuna offerta pubblicabile in questo momento.")
    else:
        for index, ranked in enumerate(snapshot.ranking.ranked[:10], start=1):
            product = ranked.candidate.product
            discount = ranked.candidate.evaluation.discount_percentage
            discount_text = f"{discount}%" if discount is not None else "N/D"
            lines.extend([
                f"<b>#{index}</b> {escape(product.title[:65])}",
                f"Score {ranked.candidate.evaluation.score} + priorità {ranked.priority_bonus:+d} = <b>{ranked.final_score}</b>",
                f"Tipo: <code>{ranked.offer_type}</code> | Sconto: {discount_text}",
                "",
            ])

    lines.extend([
        "📊 Diagnostica avanzata:",
        f"• Input ranking: {snapshot.ranking.input_count}",
        f"• Blacklist/error: {snapshot.ranking.blacklist_rejected_count}",
        f"• Limiti: {snapshot.ranking.limit_rejected_count}",
        f"• Failed protetti: {snapshot.ranking.failed_rejected_count}",
        f"• Evento attivo: {'Sì' if snapshot.event_active else 'No'}",
    ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Aggiorna", callback_data="autopost:adv_live")],
        [InlineKeyboardButton(text="⬅️ Avanzate", callback_data="autopost:advanced")],
    ])
    if query.message is not None:
        await query.message.edit_text("\n".join(lines), reply_markup=keyboard)
    await query.answer()
