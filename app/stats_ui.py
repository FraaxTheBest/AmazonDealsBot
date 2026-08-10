from datetime import timezone
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from app.analytics_store import StatsSnapshot, get_stats_snapshot, scan_diagnostics
from app.config import get_settings
from app.database import get_channel, list_channels


router = Router(name="stats")


PERIODS = {
    "today": "Oggi",
    "7d": "7 giorni",
    "30d": "30 giorni",
    "all": "Tutto",
}


def _keyboard(
    channels,
    period: str,
    selected_channel_id: int | None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=("✅ " if period == key else "") + label,
                callback_data=f"stats:period:{key}",
            )
            for key, label in list(PERIODS.items())[:2]
        ],
        [
            InlineKeyboardButton(
                text=("✅ " if period == key else "") + label,
                callback_data=f"stats:period:{key}",
            )
            for key, label in list(PERIODS.items())[2:]
        ],
        [
            InlineKeyboardButton(
                text=("✅ " if selected_channel_id is None else "") + "Tutti i canali",
                callback_data="stats:channel:all",
            )
        ],
    ]

    for channel in channels[:15]:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        ("✅ " if selected_channel_id == channel.id else "")
                        + f"📢 {channel.title[:30]}"
                    ),
                    callback_data=f"stats:channel:{channel.id}",
                )
            ]
        )

    rows.extend(
        [
            [
                InlineKeyboardButton(text="📜 Storico", callback_data="stats:history"),
                InlineKeyboardButton(text="🧪 Diagnostica", callback_data="stats:diagnostics"),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Aggiorna",
                    callback_data="stats:refresh",
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="menu:home",
                ),
            ]
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _top_lines(items: tuple[tuple[str, int], ...]) -> str:
    if not items:
        return "—"
    return ", ".join(f"{escape(name)} ({count})" for name, count in items)


def _text(snapshot: StatsSnapshot, channel_title: str | None) -> str:
    scope = escape(channel_title) if channel_title else "Tutti i canali"
    error_total = snapshot.publish_errors + snapshot.scheduled_errors

    recent_lines = []
    for item in snapshot.recent_publications[:5]:
        dt = item.published_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        recent_lines.append(
            f"• {escape(item.title[:42])} — <code>{escape(item.asin)}</code>"
        )
    recent = "\n".join(recent_lines) if recent_lines else "—"

    return (
        "📊 <b>Statistiche</b>\n\n"
        f"📍 Ambito: <b>{scope}</b>\n"
        f"🗓 Periodo: <b>{escape(snapshot.period_label)}</b>\n\n"
        f"📤 Pubblicati: <b>{snapshot.published_total}</b>\n"
        f"   🤖 Autopost: {snapshot.published_autopost}\n"
        f"   ✋ Manuali: {snapshot.published_manual}\n"
        f"   🕒 Programmati: {snapshot.published_scheduled}\n"
        f"🗓 Programmati in attesa: <b>{snapshot.scheduled_pending}</b>\n\n"
        f"🔎 Scansioni: <b>{snapshot.scans}</b>\n"
        f"📦 Prodotti analizzati: <b>{snapshot.offers_scanned}</b>\n"
        f"✅ Deal validi: <b>{snapshot.deals_valid}</b>\n"
        f"♻️ Duplicati evitati: <b>{snapshot.duplicates_avoided}</b>\n"
        f"🚫 Blacklist: <b>{snapshot.blacklist_rejected}</b>\n"
        f"📏 Limiti: <b>{snapshot.limit_rejected}</b>\n\n"
        f"📥 Coda: {snapshot.queue_pending} attesa • "
        f"{snapshot.queue_approved} approvati • "
        f"{snapshot.queue_rejected} scartati\n"
        f"⚠️ Errori: <b>{error_total}</b>\n\n"
        f"🗂 Top categorie: {_top_lines(snapshot.top_categories)}\n"
        f"🏷 Top brand: {_top_lines(snapshot.top_brands)}\n\n"
        "🕘 <b>Ultime pubblicazioni</b>\n"
        f"{recent}"
    )


async def _show(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    period = str(data.get("stats_period", "7d"))
    selected = data.get("stats_channel_id")
    selected_channel_id = int(selected) if selected is not None else None

    channels = await list_channels(settings.admin_user_id)
    channel_title = None
    if selected_channel_id is not None:
        channel = await get_channel(selected_channel_id, settings.admin_user_id)
        if channel is None:
            selected_channel_id = None
            await state.update_data(stats_channel_id=None)
        else:
            channel_title = channel.title

    snapshot = await get_stats_snapshot(
        settings.admin_user_id,
        channel_id=selected_channel_id,
        period=period,
    )

    if query.message is not None:
        await query.message.edit_text(
            _text(snapshot, channel_title),
            reply_markup=_keyboard(channels, period, selected_channel_id),
        )
    await query.answer()


@router.callback_query(F.data == "menu:stats")
async def stats_open(query: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(stats_period="7d", stats_channel_id=None)
    await _show(query, state)


@router.callback_query(F.data.startswith("stats:period:"))
async def stats_period(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data:
        return
    period = query.data.rsplit(":", 1)[-1]
    if period not in PERIODS:
        await query.answer("Periodo non valido.", show_alert=True)
        return
    await state.update_data(stats_period=period)
    await _show(query, state)


@router.callback_query(F.data.startswith("stats:channel:"))
async def stats_channel(query: CallbackQuery, state: FSMContext) -> None:
    if not query.data:
        return
    value = query.data.rsplit(":", 1)[-1]
    await state.update_data(
        stats_channel_id=None if value == "all" else int(value)
    )
    await _show(query, state)


@router.callback_query(F.data == "stats:refresh")
async def stats_refresh(query: CallbackQuery, state: FSMContext) -> None:
    await _show(query, state)


@router.callback_query(F.data == "stats:diagnostics")
async def stats_diagnostics(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    period = str(data.get("stats_period", "7d"))
    selected = data.get("stats_channel_id")
    channel_id = int(selected) if selected is not None else None
    values = await scan_diagnostics(
        settings.admin_user_id,
        channel_id=channel_id,
        period=period,
    )
    text = (
        "🧪 <b>Diagnostica pipeline</b>\n\n"
        f"Scansioni: <b>{values['scans']}</b>\n"
        f"Prodotti ricevuti: <b>{values['source']}</b>\n"
        f"Deal validi: <b>{values['deals']}</b>\n"
        f"Duplicati evitati: <b>{values['duplicates']}</b>\n"
        f"Blacklist: <b>{values['blacklist']}</b>\n"
        f"Limiti: <b>{values['limits']}</b>\n"
        f"Pubblicati: <b>{values['published']}</b>\n"
        f"Errori: <b>{values['errors']}</b>"
    )
    if query.message is not None:
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Statistiche", callback_data="menu:stats")],
            ]),
        )
    await query.answer()
