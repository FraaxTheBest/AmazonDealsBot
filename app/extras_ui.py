from datetime import timezone
from html import escape, unescape
import re

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.autopost_advanced_store import (
    BLACKLIST_ASIN,
    BLACKLIST_BRAND,
    BLACKLIST_SELLER,
    add_blacklist_entry,
)
from app.autopost_auto_service import live_ranking_snapshot
from app.config import get_settings
from app.database import list_channels
from app.dedupe_store import record_publication
from app.drafts_store import (
    STATUS_OPEN,
    claim_draft_for_publish,
    create_draft,
    discard_draft,
    draft_product,
    get_owner_draft,
    list_open_drafts,
    mark_draft_failed_terminal,
    mark_draft_published,
    restore_draft_open,
)
from app.publisher import send_product_post
from app.scheduled_store import create_scheduled_post
from app.scheduler_service import schedule_post_job
from app.scheduling import parse_local_datetime
from app.shortlink_service import build_offer_url
from app.template_engine import DEFAULT_POST_TEMPLATE, render_template
from app.template_store import get_default_template_content


router = Router(name="extras")


class ExtraStates(StatesGroup):
    waiting_schedule = State()


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Home", callback_data="menu:home")
    ]])


def channels_keyboard(prefix: str, channels) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(
        text=f"📢 {channel.title[:34]}",
        callback_data=f"{prefix}:{channel.id}",
    )] for channel in channels]
    rows.append([InlineKeyboardButton(text="⬅️ Impostazioni", callback_data="menu:settings")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def extras_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Azioni miglior offerta", callback_data="extras:best_channels")],
        [InlineKeyboardButton(text="📝 Bozze", callback_data="extras:drafts")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="menu:home")],
    ])


def best_keyboard(channel_id: int, product) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="📝 Salva bozza", callback_data=f"extras:best_draft:{channel_id}")],
        [InlineKeyboardButton(text="📅 Programma", callback_data=f"extras:best_schedule:{channel_id}")],
    ]
    if product.brand:
        rows.append([InlineKeyboardButton(text="🚫 Blocca brand", callback_data=f"extras:best_brand:{channel_id}")])
    if product.seller:
        rows.append([InlineKeyboardButton(text="🚫 Blocca venditore", callback_data=f"extras:best_seller:{channel_id}")])
    rows.append([InlineKeyboardButton(text="🚫 Blocca questo ASIN", callback_data=f"extras:best_asin:{channel_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Extra", callback_data="settings:extras")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _best_product(owner_id: int, channel_id: int):
    snapshot = await live_ranking_snapshot(owner_id, channel_id)
    if not snapshot.ranking.ranked:
        return None, snapshot
    return snapshot.ranking.ranked[0].candidate.product, snapshot


async def _render(product, owner_id: int) -> str:
    template = await get_default_template_content(owner_id, DEFAULT_POST_TEMPLATE)
    try:
        return render_template(template, product)
    except ValueError:
        return render_template(DEFAULT_POST_TEMPLATE, product)


@router.callback_query(F.data == "settings:extras")
async def open_extras(query: CallbackQuery) -> None:
    if query.message:
        await query.message.edit_text(
            "🧰 <b>Extra</b>\n\n"
            "Qui trovi le azioni meno frequenti: bozze, programmazione dalla classifica e blocchi rapidi.",
            reply_markup=extras_keyboard(),
        )
    await query.answer()


@router.callback_query(F.data == "extras:best_channels")
async def choose_best_channel(query: CallbackQuery) -> None:
    settings = get_settings()
    channels = await list_channels(settings.admin_user_id)
    if query.message:
        await query.message.edit_text(
            "🏆 <b>Miglior offerta</b>\n\nScegli il canale:",
            reply_markup=channels_keyboard("extras:best", channels),
        )
    await query.answer()


@router.callback_query(F.data.startswith("extras:best:"))
async def show_best(query: CallbackQuery) -> None:
    settings = get_settings()
    channel_id = int(query.data.rsplit(":", 1)[1])
    product, snapshot = await _best_product(settings.admin_user_id, channel_id)
    if product is None:
        await query.answer("Nessuna offerta valida adesso.", show_alert=True)
        return
    ranked = snapshot.ranking.ranked[0]
    text = (
        "🏆 <b>Miglior candidato live</b>\n\n"
        f"<b>{escape(product.title)}</b>\n"
        f"ASIN: <code>{escape(product.asin)}</code>\n"
        f"Score: <b>{ranked.final_score}</b>\n"
        f"Tipo: <b>{escape(ranked.offer_type)}</b>"
    )
    if query.message:
        await query.message.edit_text(text, reply_markup=best_keyboard(channel_id, product))
    await query.answer()


@router.callback_query(F.data.startswith("extras:best_draft:"))
async def best_to_draft(query: CallbackQuery) -> None:
    settings = get_settings()
    channel_id = int(query.data.rsplit(":", 1)[1])
    product, _ = await _best_product(settings.admin_user_id, channel_id)
    if product is None:
        await query.answer("Nessun candidato.", show_alert=True)
        return
    text = await _render(product, settings.admin_user_id)
    draft = await create_draft(settings.admin_user_id, channel_id, product, text, source="live")
    await query.answer(f"Bozza #{draft.id} salvata.", show_alert=True)


@router.callback_query(F.data.startswith("extras:best_schedule:"))
async def best_schedule_start(query: CallbackQuery, state: FSMContext) -> None:
    channel_id = int(query.data.rsplit(":", 1)[1])
    await state.update_data(extra_schedule_channel_id=channel_id)
    await state.set_state(ExtraStates.waiting_schedule)
    if query.message:
        await query.message.edit_text(
            "📅 <b>Programma miglior offerta</b>\n\n"
            "Invia data e ora nel formato:\n<code>10/08/2026 21:30</code>\n\n"
            "Il prodotto verrà salvato adesso e ricontrollato prima della pubblicazione.",
            reply_markup=home_keyboard(),
        )
    await query.answer()


@router.message(ExtraStates.waiting_schedule)
async def best_schedule_receive(message: Message, state: FSMContext) -> None:
    if not message.text:
        return
    settings = get_settings()
    data = await state.get_data()
    channel_id = int(data["extra_schedule_channel_id"])
    try:
        local = parse_local_datetime(message.text)
    except ValueError:
        await message.answer("Formato non valido. Usa GG/MM/AAAA HH:MM.")
        return
    product, _ = await _best_product(settings.admin_user_id, channel_id)
    if product is None:
        await state.clear()
        await message.answer("Nessun candidato disponibile.")
        return
    text = await _render(product, settings.admin_user_id)
    post = await create_scheduled_post(
        settings.admin_user_id,
        channel_id,
        local.astimezone(timezone.utc),
        product,
        text,
    )
    schedule_post_job(post.id, post.run_at)
    await state.clear()
    await message.answer(f"✅ Post #{post.id} programmato.", reply_markup=home_keyboard())


async def _block_best(query: CallbackQuery, kind: str) -> None:
    settings = get_settings()
    channel_id = int(query.data.rsplit(":", 1)[1])
    product, _ = await _best_product(settings.admin_user_id, channel_id)
    if product is None:
        await query.answer("Nessun candidato.", show_alert=True)
        return
    values = {
        BLACKLIST_BRAND: product.brand,
        BLACKLIST_SELLER: product.seller,
        BLACKLIST_ASIN: product.asin,
    }
    value = values.get(kind)
    if not value:
        await query.answer("Dato non disponibile.", show_alert=True)
        return
    await add_blacklist_entry(settings.admin_user_id, channel_id, kind, value)
    await query.answer("Blocco aggiunto.", show_alert=True)


@router.callback_query(F.data.startswith("extras:best_brand:"))
async def block_brand(query: CallbackQuery) -> None:
    await _block_best(query, BLACKLIST_BRAND)


@router.callback_query(F.data.startswith("extras:best_seller:"))
async def block_seller(query: CallbackQuery) -> None:
    await _block_best(query, BLACKLIST_SELLER)


@router.callback_query(F.data.startswith("extras:best_asin:"))
async def block_asin(query: CallbackQuery) -> None:
    await _block_best(query, BLACKLIST_ASIN)


def drafts_keyboard(rows) -> InlineKeyboardMarkup:
    kb = []
    for draft, channel in rows[:20]:
        kb.append([InlineKeyboardButton(
            text=f"📝 #{draft.id} • {channel.title[:20]}",
            callback_data=f"extras:draft:{draft.id}",
        )])
    if len(rows) >= 2:
        kb.append([InlineKeyboardButton(text="🧩 Pubblica primi 3 insieme", callback_data="extras:drafts_multi")])
    kb.append([InlineKeyboardButton(text="⬅️ Extra", callback_data="settings:extras")])
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.callback_query(F.data == "extras:drafts")
async def show_drafts(query: CallbackQuery) -> None:
    settings = get_settings()
    rows = await list_open_drafts(settings.admin_user_id, limit=50)
    text = "📝 <b>Bozze</b>\n\n"
    text += "Nessuna bozza aperta." if not rows else f"Bozze aperte: <b>{len(rows)}</b>"
    if query.message:
        await query.message.edit_text(text, reply_markup=drafts_keyboard(rows))
    await query.answer()


def draft_detail_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Pubblica", callback_data=f"extras:draft_publish:{draft_id}")],
        [InlineKeyboardButton(text="🗑 Scarta", callback_data=f"extras:draft_discard:{draft_id}")],
        [InlineKeyboardButton(text="⬅️ Bozze", callback_data="extras:drafts")],
    ])


@router.callback_query(F.data.startswith("extras:draft:"))
async def draft_detail(query: CallbackQuery) -> None:
    settings = get_settings()
    draft_id = int(query.data.rsplit(":", 1)[1])
    row = await get_owner_draft(settings.admin_user_id, draft_id)
    if row is None:
        await query.answer("Bozza non trovata.", show_alert=True)
        return
    draft, channel = row
    if query.message:
        await query.message.edit_text(
            f"📝 <b>Bozza #{draft.id}</b>\n📢 {escape(channel.title)}\n\n{draft.post_text[:2500]}",
            reply_markup=draft_detail_keyboard(draft.id),
        )
    await query.answer()


@router.callback_query(F.data.startswith("extras:draft_discard:"))
async def draft_discard(query: CallbackQuery) -> None:
    settings = get_settings()
    draft_id = int(query.data.rsplit(":", 1)[1])
    ok = await discard_draft(settings.admin_user_id, draft_id)
    await query.answer("Bozza scartata." if ok else "Bozza non disponibile.", show_alert=True)


@router.callback_query(F.data.startswith("extras:draft_publish:"))
async def draft_publish(query: CallbackQuery, bot: Bot) -> None:
    settings = get_settings()
    draft_id = int(query.data.rsplit(":", 1)[1])
    row = await get_owner_draft(settings.admin_user_id, draft_id)
    if row is None:
        await query.answer("Bozza non trovata.", show_alert=True)
        return
    draft, channel = row
    if draft.status != STATUS_OPEN:
        await query.answer("Bozza già gestita.", show_alert=True)
        return
    claimed = await claim_draft_for_publish(settings.admin_user_id, draft.id)
    if not claimed:
        await query.answer("Bozza già in gestione.", show_alert=True)
        return

    product = draft_product(draft)
    sent = None
    try:
        url = await build_offer_url(
            owner_telegram_user_id=settings.admin_user_id,
            channel_id=channel.id,
            product=product,
        )
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        markup = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Vedi offerta 👀", url=url)
        ]])
        sent = await send_product_post(
            bot,
            channel.telegram_chat_id,
            product,
            draft.post_text,
            markup,
        )
    except Exception as exc:
        await restore_draft_open(settings.admin_user_id, draft.id)
        await query.answer(
            f"Pubblicazione fallita: {str(exc)[:120]}",
            show_alert=True,
        )
        return

    # Telegram ha già ricevuto: da qui nessun retry automatico.
    try:
        marked = await mark_draft_published(settings.admin_user_id, draft.id)
        if not marked:
            await mark_draft_failed_terminal(settings.admin_user_id, draft.id)
    except Exception:
        await mark_draft_failed_terminal(settings.admin_user_id, draft.id)

    try:
        await record_publication(
            settings.admin_user_id,
            channel.id,
            product,
            "draft",
            sent.message_id,
        )
    except Exception:
        pass
    await query.answer("Bozza pubblicata.", show_alert=True)


@router.callback_query(F.data == "extras:drafts_multi")
async def drafts_multi(query: CallbackQuery, bot: Bot) -> None:
    settings = get_settings()
    rows = await list_open_drafts(settings.admin_user_id, limit=50)
    if len(rows) < 2:
        await query.answer("Servono almeno 2 bozze.", show_alert=True)
        return
    first_channel = rows[0][1]
    selected = [(d, c) for d, c in rows if c.id == first_channel.id][:3]
    if len(selected) < 2:
        await query.answer("Servono almeno 2 bozze nello stesso canale.", show_alert=True)
        return
    # Il post multiplo deve restare sotto il limite Telegram e non deve
    # troncare tag HTML a metà. Convertiamo quindi ogni bozza in testo
    # semplice, poi riapplichiamo soltanto l'escaping sicuro.
    parts: list[str] = []
    max_total = 3800
    separator = "\n\n━━━━━━━━━━\n\n"

    for index, (draft, _channel) in enumerate(selected, 1):
        plain = re.sub(r"<[^>]+>", "", draft.post_text)
        plain = unescape(plain).strip()
        if len(plain) > 1100:
            plain = plain[:1097].rstrip() + "…"
        part = f"<b>{index}.</b> {escape(plain)}"

        candidate_text = separator.join([*parts, part])
        if len(candidate_text) > max_total:
            break
        parts.append(part)

    if len(parts) < 2:
        await query.answer(
            "Le bozze sono troppo lunghe per un singolo post multiplo.",
            show_alert=True,
        )
        return

    selected = selected[:len(parts)]
    combined_text = separator.join(parts)

    claimed_rows = []
    for draft, channel in selected:
        if await claim_draft_for_publish(settings.admin_user_id, draft.id):
            claimed_rows.append((draft, channel))

    if len(claimed_rows) < 2:
        for draft, _channel in claimed_rows:
            await restore_draft_open(settings.admin_user_id, draft.id)
        await query.answer("Le bozze sono già in gestione.", show_alert=True)
        return

    # Ricostruiamo il messaggio solo con le bozze effettivamente bloccate.
    claimed_ids = {draft.id for draft, _channel in claimed_rows}
    final_parts = [
        part
        for part, (draft, _channel) in zip(parts, selected)
        if draft.id in claimed_ids
    ]
    combined_text = separator.join(final_parts)

    try:
        sent = await bot.send_message(
            first_channel.telegram_chat_id,
            combined_text,
            disable_web_page_preview=True,
        )
    except Exception as exc:
        for draft, _channel in claimed_rows:
            await restore_draft_open(settings.admin_user_id, draft.id)
        await query.answer(
            f"Post multiplo fallito: {str(exc)[:120]}",
            show_alert=True,
        )
        return

    for draft, channel in claimed_rows:
        product = draft_product(draft)
        try:
            marked = await mark_draft_published(settings.admin_user_id, draft.id)
            if not marked:
                await mark_draft_failed_terminal(settings.admin_user_id, draft.id)
        except Exception:
            await mark_draft_failed_terminal(settings.admin_user_id, draft.id)
        try:
            await record_publication(
                settings.admin_user_id,
                channel.id,
                product,
                "multi",
                sent.message_id,
            )
        except Exception:
            pass
    await query.answer(
        f"Pubblicate {len(claimed_rows)} bozze in un post.",
        show_alert=True,
    )
