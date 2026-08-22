from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.config import get_settings
from app.social.base import SocialPost
from app.social_service import PLATFORM_LABELS, SocialService
from app.social_store import (
    STATUS_FAILED,
    STATUS_OPEN,
    STATUS_PARTIAL,
    STATUS_PUBLISHED,
    create_social_draft,
    get_social_draft,
    list_social_drafts,
    toggle_social_destination,
    update_social_field,
)


router = Router(name="social")


class SocialStates(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_link = State()
    waiting_image_url = State()
    waiting_hashtags = State()
    waiting_edit_value = State()


STATUS_ICONS = {
    STATUS_OPEN: "📝",
    STATUS_PUBLISHED: "✅",
    STATUS_PARTIAL: "🟡",
    STATUS_FAILED: "❌",
}


FIELD_LABELS = {
    "title": "Titolo",
    "description": "Descrizione",
    "link": "Link",
    "image_url": "URL immagine",
    "hashtags": "Hashtag",
}


def _blank(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value == "-" else value


def _service() -> SocialService:
    return SocialService(get_settings())




async def _safe_edit(message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


def social_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Nuovo post social", callback_data="social:new")],
        [InlineKeyboardButton(text="📝 Bozze social", callback_data="social:drafts")],
        [InlineKeyboardButton(text="📱 Destinazioni", callback_data="social:status")],
        [InlineKeyboardButton(text="🏠 Home", callback_data="menu:home")],
    ])


def social_home_text() -> str:
    statuses = _service().statuses()
    lines = ["🌐 <b>Social Hub</b>", "", "Stato piattaforme:"]
    for platform in ("facebook", "instagram", "pinterest", "telegram", "whatsapp"):
        ready, reason = statuses[platform]
        icon = "✅" if ready else "🔒"
        lines.append(f"{icon} <b>{PLATFORM_LABELS[platform]}</b> — {escape(reason)}")
    lines.extend(["", "Puoi pubblicare solo sulle piattaforme attualmente pronte."])
    return "\n".join(lines)


def _draft_text(draft) -> str:
    selected = set(draft.destinations())
    destinations = []
    for platform in ("facebook", "instagram", "pinterest", "telegram", "whatsapp"):
        destinations.append(
            f"{'✅' if platform in selected else '⬜'} {PLATFORM_LABELS[platform]}"
        )

    return (
        f"📝 <b>Bozza Social #{draft.id}</b>\n\n"
        f"<b>Titolo:</b> {escape(draft.title or '—')}\n"
        f"<b>Descrizione:</b> {escape(draft.description or '—')}\n"
        f"<b>Link:</b> {escape(draft.link or '—')}\n"
        f"<b>Immagine:</b> {escape(draft.image_url or '—')}\n"
        f"<b>Hashtag:</b> {escape(draft.hashtags or '—')}\n\n"
        f"<b>Destinazioni</b>\n" + "\n".join(destinations) +
        f"\n\nStato: <b>{escape(draft.status)}</b>"
    )


def draft_keyboard(draft) -> InlineKeyboardMarkup:
    service = _service()
    selected = set(draft.destinations())
    rows: list[list[InlineKeyboardButton]] = []

    for platform in ("facebook", "instagram", "pinterest", "telegram", "whatsapp"):
        ready, _reason = service.platform_status(platform)
        label = PLATFORM_LABELS[platform]
        if ready:
            icon = "✅" if platform in selected else "⬜"
            callback = f"social:toggle:{draft.id}:{platform}"
        else:
            icon = "🔒"
            callback = f"social:locked:{platform}"
        rows.append([InlineKeyboardButton(text=f"{icon} {label}", callback_data=callback)])

    rows.extend([
        [InlineKeyboardButton(text="✏️ Modifica", callback_data=f"social:edit:{draft.id}")],
        [InlineKeyboardButton(text="👁 Anteprima", callback_data=f"social:preview:{draft.id}")],
        [InlineKeyboardButton(text="🚀 Pubblica sugli attivi", callback_data=f"social:publish:{draft.id}")],
        [InlineKeyboardButton(text="⬅️ Social Hub", callback_data="menu:social")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_keyboard(draft_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Titolo", callback_data=f"social:edit_field:{draft_id}:title")],
        [InlineKeyboardButton(text="📄 Descrizione", callback_data=f"social:edit_field:{draft_id}:description")],
        [InlineKeyboardButton(text="🔗 Link", callback_data=f"social:edit_field:{draft_id}:link")],
        [InlineKeyboardButton(text="🖼 URL immagine", callback_data=f"social:edit_field:{draft_id}:image_url")],
        [InlineKeyboardButton(text="#️⃣ Hashtag", callback_data=f"social:edit_field:{draft_id}:hashtags")],
        [InlineKeyboardButton(text="⬅️ Bozza", callback_data=f"social:draft:{draft_id}")],
    ])


@router.callback_query(F.data == "menu:social")
async def open_social(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if not get_settings().social_enabled:
        await query.answer("Social Hub disattivato nel .env.", show_alert=True)
        return
    if query.message:
        await _safe_edit(query.message, social_home_text(), reply_markup=social_home_keyboard())
    await query.answer()


@router.callback_query(F.data == "social:status")
async def social_status(query: CallbackQuery) -> None:
    if query.message:
        await _safe_edit(query.message, social_home_text(), reply_markup=social_home_keyboard())
    await query.answer()


@router.callback_query(F.data.startswith("social:locked:"))
async def locked_platform(query: CallbackQuery) -> None:
    platform = query.data.rsplit(":", 1)[1]
    ready, reason = _service().platform_status(platform)
    if ready:
        await query.answer("Piattaforma pronta.", show_alert=True)
    else:
        await query.answer(f"🔒 {PLATFORM_LABELS.get(platform, platform)}\n{reason}", show_alert=True)


@router.callback_query(F.data == "social:new")
async def new_post(query: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SocialStates.waiting_title)
    if query.message:
        await query.message.edit_text(
            "➕ <b>Nuovo post social</b>\n\n1/5 Invia il <b>titolo</b>.\nUsa <code>-</code> per lasciarlo vuoto.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Annulla", callback_data="menu:social")
            ]]),
        )
    await query.answer()


@router.message(SocialStates.waiting_title)
async def receive_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=_blank(message.text))
    await state.set_state(SocialStates.waiting_description)
    await message.answer("2/5 Invia la <b>descrizione</b>. Usa <code>-</code> per vuoto.")


@router.message(SocialStates.waiting_description)
async def receive_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=_blank(message.text))
    await state.set_state(SocialStates.waiting_link)
    await message.answer("3/5 Invia il <b>link</b>. Usa <code>-</code> per vuoto.")


@router.message(SocialStates.waiting_link)
async def receive_link(message: Message, state: FSMContext) -> None:
    await state.update_data(link=_blank(message.text))
    await state.set_state(SocialStates.waiting_image_url)
    await message.answer(
        "4/5 Invia l'<b>URL pubblico dell'immagine</b>.\n\n"
        "Per Instagram e' necessario un URL pubblico (es. immagine del Pin).\n"
        "Usa <code>-</code> se vuoi creare una bozza senza immagine."
    )


@router.message(SocialStates.waiting_image_url)
async def receive_image_url(message: Message, state: FSMContext) -> None:
    await state.update_data(image_url=_blank(message.text))
    await state.set_state(SocialStates.waiting_hashtags)
    await message.answer("5/5 Invia gli <b>hashtag</b>. Usa <code>-</code> per vuoto.")


@router.message(SocialStates.waiting_hashtags)
async def receive_hashtags(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    post = SocialPost(
        title=data.get("title", ""),
        description=data.get("description", ""),
        link=data.get("link", ""),
        image_url=data.get("image_url", ""),
        hashtags=_blank(message.text),
    )
    service = _service()
    destinations = service.ready_platforms()
    draft = await create_social_draft(settings.admin_user_id, post, destinations)
    await state.clear()
    await message.answer(_draft_text(draft), reply_markup=draft_keyboard(draft))


@router.callback_query(F.data == "social:drafts")
async def show_drafts(query: CallbackQuery) -> None:
    settings = get_settings()
    drafts = await list_social_drafts(settings.admin_user_id, limit=20)
    rows: list[list[InlineKeyboardButton]] = []
    for draft in drafts:
        icon = STATUS_ICONS.get(draft.status, "📝")
        title = (draft.title or "Senza titolo")[:28]
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} #{draft.id} • {title}",
                callback_data=f"social:draft:{draft.id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Social Hub", callback_data="menu:social")])
    text = "📝 <b>Bozze social</b>\n\n" + (f"Ultime bozze: <b>{len(drafts)}</b>" if drafts else "Nessuna bozza social.")
    if query.message:
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await query.answer()


@router.callback_query(F.data.startswith("social:draft:"))
async def show_draft(query: CallbackQuery) -> None:
    settings = get_settings()
    draft_id = int(query.data.rsplit(":", 1)[1])
    draft = await get_social_draft(settings.admin_user_id, draft_id)
    if draft is None:
        await query.answer("Bozza non trovata.", show_alert=True)
        return
    if query.message:
        await query.message.edit_text(_draft_text(draft), reply_markup=draft_keyboard(draft))
    await query.answer()


@router.callback_query(F.data.startswith("social:toggle:"))
async def toggle_destination(query: CallbackQuery) -> None:
    settings = get_settings()
    _prefix, _toggle, draft_id_text, platform = query.data.split(":", 3)
    ready, reason = _service().platform_status(platform)
    if not ready:
        await query.answer(f"🔒 {reason}", show_alert=True)
        return
    draft = await toggle_social_destination(settings.admin_user_id, int(draft_id_text), platform)
    if draft is None:
        await query.answer("Bozza non trovata.", show_alert=True)
        return
    if query.message:
        await query.message.edit_text(_draft_text(draft), reply_markup=draft_keyboard(draft))
    await query.answer()


@router.callback_query(F.data.startswith("social:edit:"))
async def edit_draft(query: CallbackQuery) -> None:
    draft_id = int(query.data.rsplit(":", 1)[1])
    if query.message:
        await query.message.edit_text(
            "✏️ <b>Modifica bozza social</b>\n\nScegli il campo da modificare:",
            reply_markup=edit_keyboard(draft_id),
        )
    await query.answer()


@router.callback_query(F.data.startswith("social:edit_field:"))
async def edit_field(query: CallbackQuery, state: FSMContext) -> None:
    parts = query.data.split(":", 3)
    draft_id = int(parts[2])
    field = parts[3]
    if field not in FIELD_LABELS:
        await query.answer("Campo non valido.", show_alert=True)
        return
    await state.update_data(edit_draft_id=draft_id, edit_field=field)
    await state.set_state(SocialStates.waiting_edit_value)
    if query.message:
        await query.message.edit_text(
            f"✏️ Invia il nuovo valore per <b>{escape(FIELD_LABELS[field])}</b>.\n"
            "Usa <code>-</code> per svuotare il campo."
        )
    await query.answer()


@router.message(SocialStates.waiting_edit_value)
async def receive_edit_value(message: Message, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    draft_id = int(data["edit_draft_id"])
    field = str(data["edit_field"])
    draft = await update_social_field(settings.admin_user_id, draft_id, field, _blank(message.text))
    await state.clear()
    if draft is None:
        await message.answer("Bozza non trovata.")
        return
    await message.answer(_draft_text(draft), reply_markup=draft_keyboard(draft))


@router.callback_query(F.data.startswith("social:preview:"))
async def preview_draft(query: CallbackQuery) -> None:
    settings = get_settings()
    draft_id = int(query.data.rsplit(":", 1)[1])
    draft = await get_social_draft(settings.admin_user_id, draft_id)
    if draft is None:
        await query.answer("Bozza non trovata.", show_alert=True)
        return
    preview = draft.post().text(include_link=True, include_hashtags=True) or "(post vuoto)"
    text = (
        f"👁 <b>Anteprima bozza #{draft.id}</b>\n\n"
        f"{escape(preview[:3000])}\n\n"
        f"🖼 <b>Immagine:</b> {escape(draft.image_url or '—')}"
    )
    if query.message:
        await query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⬅️ Bozza", callback_data=f"social:draft:{draft.id}")
            ]]),
        )
    await query.answer()


@router.callback_query(F.data.startswith("social:publish:"))
async def publish_draft(query: CallbackQuery) -> None:
    settings = get_settings()
    draft_id = int(query.data.rsplit(":", 1)[1])
    draft = await get_social_draft(settings.admin_user_id, draft_id)
    if draft is None:
        await query.answer("Bozza non trovata.", show_alert=True)
        return
    if draft.status == STATUS_PUBLISHED:
        await query.answer("Questa bozza risulta gia' pubblicata.", show_alert=True)
        return
    if draft.status == STATUS_PARTIAL:
        await query.answer(
            "Bozza pubblicata solo in parte. Per sicurezza non ripubblichiamo automaticamente: evita duplicati. Crea una nuova bozza solo per la piattaforma fallita.",
            show_alert=True,
        )
        return

    await query.answer("Pubblicazione in corso...")
    result = await _service().publish_draft(settings.admin_user_id, draft)

    lines = [f"🚀 <b>Risultato bozza #{draft.id}</b>", ""]
    for platform in draft.destinations():
        item = result.get("results", {}).get(platform, {})
        if item.get("success"):
            icon = "✅"
        elif item.get("skipped"):
            icon = "🔒"
        else:
            icon = "❌"
        message_text = str(item.get("message") or "Nessun risultato")
        lines.append(f"{icon} <b>{PLATFORM_LABELS.get(platform, platform)}</b>: {escape(message_text[:500])}")

    fresh = await get_social_draft(settings.admin_user_id, draft.id)
    if query.message:
        await query.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📝 Torna alla bozza", callback_data=f"social:draft:{draft.id}")],
                [InlineKeyboardButton(text="🌐 Social Hub", callback_data="menu:social")],
            ]),
        )
