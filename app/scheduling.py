import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from html import escape
from zoneinfo import (
    ZoneInfo,
    ZoneInfoNotFoundError,
)

from aiogram import (
    Bot,
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

from app.amazon.models import (
    ProductSnapshot,
)
from app.config import get_settings
from app.database import get_channel
from app.posts import (
    delete_message_safely,
    get_state_product,
    home_keyboard,
    render_saved_template,
    send_preview,
)
from app.publisher import (
    PHOTO_CAPTION_LIMIT,
)
from app.scheduled_store import (
    STATUS_PENDING,
    cancel_scheduled_post,
    create_scheduled_post,
    get_owner_scheduled_post,
    list_owner_pending_posts,
    reschedule_scheduled_post,
)
from app.scheduler_service import (
    cancel_post_job,
    reschedule_post_job,
    schedule_post_job,
)


router = Router(
    name="scheduling"
)


class ScheduleStates(
    StatesGroup
):
    waiting_datetime = State()

    waiting_reschedule_datetime = (
        State()
    )


# =========================================================
# TIME HELPERS
# =========================================================


def get_local_timezone(
) -> ZoneInfo:
    settings = get_settings()

    try:
        return ZoneInfo(
            settings.app_timezone
        )

    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            "Fuso orario non valido."
        ) from exc


def normalize_utc(
    value: datetime,
) -> datetime:
    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def to_local_time(
    value: datetime,
) -> datetime:
    return normalize_utc(
        value
    ).astimezone(
        get_local_timezone()
    )


def parse_local_datetime(
    value: str,
) -> datetime:
    local_timezone = (
        get_local_timezone()
    )

    return (
        datetime.strptime(
            value.strip(),
            "%d/%m/%Y %H:%M",
        )
        .replace(
            tzinfo=local_timezone
        )
    )


# =========================================================
# KEYBOARDS
# =========================================================


def schedule_input_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "↩️ Torna "
                        "all'anteprima"
                    ),
                    callback_data=(
                        "post:schedule_back"
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


def scheduled_posts_keyboard(
    posts: list,
) -> InlineKeyboardMarkup:
    rows = []

    for post, channel in posts:
        run_at_local = (
            to_local_time(
                post.run_at
            )
        )

        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"🕒 "
                        f"{run_at_local.strftime('%d/%m %H:%M')}"
                        f" • "
                        f"{channel.title[:22]}"
                    ),
                    callback_data=(
                        "schedule:detail:"
                        f"{post.id}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Aggiorna",
                callback_data=(
                    "menu:scheduled"
                ),
            )
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 Home",
                callback_data=(
                    "menu:home"
                ),
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def scheduled_empty_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Crea Post",
                    callback_data=(
                        "menu:create_post"
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


def scheduled_detail_keyboard(
    post_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🕒 Cambia orario",
                    callback_data=(
                        "schedule:edit:"
                        f"{post_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Annulla",
                    callback_data=(
                        "schedule:cancel:"
                        f"{post_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Lista",
                    callback_data=(
                        "menu:scheduled"
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


def cancel_confirmation_keyboard(
    post_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "✅ Sì, annulla"
                    ),
                    callback_data=(
                        "schedule:cancel_yes:"
                        f"{post_id}"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "❌ No, torna indietro"
                    ),
                    callback_data=(
                        "schedule:detail:"
                        f"{post_id}"
                    ),
                )
            ],
        ]
    )


def reschedule_keyboard(
    post_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Annulla modifica",
                    callback_data=(
                        "schedule:detail:"
                        f"{post_id}"
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


def scheduled_created_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "🗓 Post programmati"
                    ),
                    callback_data=(
                        "menu:scheduled"
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
# TEXT HELPERS
# =========================================================


def get_product_from_post(
    product_json: str,
) -> ProductSnapshot | None:
    try:
        data = json.loads(
            product_json
        )

        return (
            ProductSnapshot
            .model_validate(
                data
            )
        )

    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
    ):
        return None


def scheduled_detail_text(
    scheduled_post,
    channel,
) -> str:
    settings = get_settings()

    run_at_local = to_local_time(
        scheduled_post.run_at
    )

    product = get_product_from_post(
        scheduled_post.product_json
    )

    if product is not None:
        title = product.title

        asin = product.asin

    else:
        title = (
            "Prodotto non disponibile"
        )

        asin = "-"

    return (
        "🗓 <b>Post programmato</b>"
        "\n\n"
        f"🆔 ID: "
        f"<code>"
        f"{scheduled_post.id}"
        f"</code>\n\n"
        f"📦 Prodotto:\n"
        f"<b>{escape(title)}</b>"
        "\n\n"
        f"🔢 ASIN: "
        f"<code>{escape(asin)}</code>"
        "\n\n"
        f"📢 Canale: "
        f"<b>{escape(channel.title)}</b>"
        "\n\n"
        f"🗓 Data: "
        f"<b>"
        f"{run_at_local.strftime('%d/%m/%Y')}"
        f"</b>\n"
        f"🕒 Ora: "
        f"<b>"
        f"{run_at_local.strftime('%H:%M')}"
        f"</b>\n"
        f"🌍 "
        f"{escape(settings.app_timezone)}"
        "\n\n"
        "🟡 Stato: "
        "<b>IN CODA</b>"
    )


# =========================================================
# PROGRAMMA NUOVO POST
# =========================================================


@router.callback_query(
    F.data == "post:schedule"
)
async def schedule_post_start(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    product = (
        await get_state_product(
            state
        )
    )

    data = await state.get_data()

    channel_id = data.get(
        "channel_id"
    )

    if (
        product is None
        or channel_id is None
    ):
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    settings = get_settings()

    channel = await get_channel(
        int(channel_id),
        settings.admin_user_id,
    )

    if channel is None:
        await query.answer(
            "Canale non trovato.",
            show_alert=True,
        )

        return

    try:
        local_timezone = (
            get_local_timezone()
        )

    except ValueError:
        await query.answer(
            "Fuso orario non valido.",
            show_alert=True,
        )

        return

    example_time = (
        datetime.now(
            local_timezone
        )
        + timedelta(minutes=5)
    )

    await state.set_state(
        ScheduleStates
        .waiting_datetime
    )

    await delete_message_safely(
        query.message
    )

    await bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "🕒 <b>Programma Post</b>"
            "\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Invia data e ora nel "
            "formato:\n\n"
            "<code>"
            "GG/MM/AAAA HH:MM"
            "</code>\n\n"
            "Esempio tra circa "
            "5 minuti:\n"
            f"<code>"
            f"{example_time.strftime('%d/%m/%Y %H:%M')}"
            f"</code>\n\n"
            f"🌍 Fuso orario: "
            f"<code>"
            f"{escape(settings.app_timezone)}"
            f"</code>"
        ),
        reply_markup=(
            schedule_input_keyboard()
        ),
    )

    await query.answer()


@router.callback_query(
    F.data == "post:schedule_back"
)
async def schedule_back(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    product = (
        await get_state_product(
            state
        )
    )

    if product is None:
        await query.answer(
            "Sessione scaduta.",
            show_alert=True,
        )

        return

    await state.set_state(
        None
    )

    await delete_message_safely(
        query.message
    )

    await send_preview(
        bot=bot,
        chat_id=query.from_user.id,
        product=product,
        state=state,
    )

    await query.answer()


@router.message(
    ScheduleStates.waiting_datetime
)
async def receive_schedule_datetime(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.text:
        await message.answer(
            "❌ Invia data e ora "
            "come testo.",
            reply_markup=(
                schedule_input_keyboard()
            ),
        )

        return

    settings = get_settings()

    try:
        run_at_local = (
            parse_local_datetime(
                message.text
            )
        )

    except (
        ValueError,
        ZoneInfoNotFoundError,
    ):
        await message.answer(
            "❌ Formato non valido.\n\n"
            "Usa:\n"
            "<code>"
            "GG/MM/AAAA HH:MM"
            "</code>",
            reply_markup=(
                schedule_input_keyboard()
            ),
        )

        return

    now_local = datetime.now(
        get_local_timezone()
    )

    if run_at_local <= now_local:
        await message.answer(
            "❌ L'orario deve essere "
            "nel futuro."
        )

        return

    product = (
        await get_state_product(
            state
        )
    )

    data = await state.get_data()

    channel_id = data.get(
        "channel_id"
    )

    if (
        product is None
        or channel_id is None
    ):
        await state.clear()

        await message.answer(
            "❌ Sessione scaduta.\n"
            "Ricomincia da /start."
        )

        return

    channel = await get_channel(
        int(channel_id),
        settings.admin_user_id,
    )

    if channel is None:
        await message.answer(
            "❌ Canale non disponibile."
        )

        return

    rendered_post = (
        await render_saved_template(
            product
        )
    )

    post_text = rendered_post
    if settings.amazon_provider == "demo":
        post_text += (
            "\n\n⚠️ <i>Dati demo: provider Amazon reale "
            "non ancora collegato.</i>"
        )

    if (
        product.image_url
        and len(post_text)
        > PHOTO_CAPTION_LIMIT
    ):
        await message.answer(
            "❌ Il template è troppo "
            "lungo per una caption "
            "fotografica."
        )

        return

    run_at_utc = (
        run_at_local.astimezone(
            timezone.utc
        )
    )

    try:
        scheduled_post = (
            await create_scheduled_post(
                owner_telegram_user_id=(
                    settings.admin_user_id
                ),
                channel_id=(
                    int(channel_id)
                ),
                run_at_utc=(
                    run_at_utc
                ),
                product=product,
                post_text=post_text,
            )
        )

        schedule_post_job(
            post_id=(
                scheduled_post.id
            ),
            run_at=(
                scheduled_post.run_at
            ),
        )

    except (
        ValueError,
        RuntimeError,
    ) as exc:
        await message.answer(
            "❌ Non riesco a "
            "programmare il post.\n\n"
            f"{escape(str(exc))}"
        )

        return

    await state.clear()

    await message.answer(
        "✅ <b>Post programmato!</b>"
        "\n\n"
        f"📢 Canale: "
        f"<b>{escape(channel.title)}</b>"
        "\n"
        f"🗓 Data: "
        f"<b>"
        f"{run_at_local.strftime('%d/%m/%Y')}"
        f"</b>\n"
        f"🕒 Ora: "
        f"<b>"
        f"{run_at_local.strftime('%H:%M')}"
        f"</b>\n"
        f"🌍 "
        f"{escape(settings.app_timezone)}"
        "\n\n"
        f"🆔 ID programmazione: "
        f"<code>"
        f"{scheduled_post.id}"
        f"</code>",
        reply_markup=(
            scheduled_created_keyboard()
        ),
    )


# =========================================================
# LISTA PROGRAMMATI
# =========================================================


@router.callback_query(
    F.data == "menu:scheduled"
)
async def scheduled_posts_menu(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    await state.clear()

    posts = (
        await list_owner_pending_posts(
            settings.admin_user_id
        )
    )

    if query.message is None:
        await query.answer()
        return

    if not posts:
        await query.message.edit_text(
            "🗓 <b>Post programmati</b>"
            "\n\n"
            "📭 Non ci sono post "
            "attualmente in coda.",
            reply_markup=(
                scheduled_empty_keyboard()
            ),
        )

        await query.answer()

        return

    await query.message.edit_text(
        "🗓 <b>Post programmati</b>"
        "\n\n"
        f"📦 In coda: "
        f"<b>{len(posts)}</b>\n\n"
        "Seleziona un post per "
        "gestirlo:",
        reply_markup=(
            scheduled_posts_keyboard(
                posts
            )
        ),
    )

    await query.answer()


# =========================================================
# DETTAGLIO
# =========================================================


@router.callback_query(
    F.data.startswith(
        "schedule:detail:"
    )
)
async def scheduled_post_detail(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    post_id = int(
        query.data.split(":")[-1]
    )

    delivery = (
        await get_owner_scheduled_post(
            settings.admin_user_id,
            post_id,
        )
    )

    if delivery is None:
        await query.answer(
            "Post non trovato.",
            show_alert=True,
        )

        return

    scheduled_post, channel = (
        delivery
    )

    if (
        scheduled_post.status
        != STATUS_PENDING
    ):
        await query.answer(
            "Questo post non è più "
            "in coda.",
            show_alert=True,
        )

        return

    await state.set_state(
        None
    )

    if query.message is not None:
        await query.message.edit_text(
            scheduled_detail_text(
                scheduled_post,
                channel,
            ),
            reply_markup=(
                scheduled_detail_keyboard(
                    post_id
                )
            ),
        )

    await query.answer()


# =========================================================
# ANNULLAMENTO
# =========================================================


@router.callback_query(
    F.data.startswith(
        "schedule:cancel:"
    )
)
async def cancel_scheduled_question(
    query: CallbackQuery,
) -> None:
    if query.data is None:
        return

    post_id = int(
        query.data.split(":")[-1]
    )

    if query.message is not None:
        await query.message.edit_text(
            "🗑 <b>Annullare il post?</b>"
            "\n\n"
            "Il post verrà rimosso "
            "dalla coda e non sarà "
            "pubblicato.",
            reply_markup=(
                cancel_confirmation_keyboard(
                    post_id
                )
            ),
        )

    await query.answer()


@router.callback_query(
    F.data.startswith(
        "schedule:cancel_yes:"
    )
)
async def cancel_scheduled_confirm(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    post_id = int(
        query.data.split(":")[-1]
    )

    cancelled = (
        await cancel_scheduled_post(
            settings.admin_user_id,
            post_id,
        )
    )

    if not cancelled:
        await query.answer(
            "Il post non è più "
            "annullabile.",
            show_alert=True,
        )

        return

    cancel_post_job(
        post_id
    )

    await state.clear()

    posts = (
        await list_owner_pending_posts(
            settings.admin_user_id
        )
    )

    if query.message is not None:
        if posts:
            await query.message.edit_text(
                "✅ <b>Post annullato.</b>"
                "\n\n"
                f"📦 Rimasti in coda: "
                f"<b>{len(posts)}</b>",
                reply_markup=(
                    scheduled_posts_keyboard(
                        posts
                    )
                ),
            )

        else:
            await query.message.edit_text(
                "✅ <b>Post annullato.</b>"
                "\n\n"
                "📭 La coda ora è vuota.",
                reply_markup=(
                    scheduled_empty_keyboard()
                ),
            )

    await query.answer(
        "Post annullato!"
    )


# =========================================================
# CAMBIA ORARIO
# =========================================================


@router.callback_query(
    F.data.startswith(
        "schedule:edit:"
    )
)
async def edit_scheduled_time(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    if query.data is None:
        return

    settings = get_settings()

    post_id = int(
        query.data.split(":")[-1]
    )

    delivery = (
        await get_owner_scheduled_post(
            settings.admin_user_id,
            post_id,
        )
    )

    if delivery is None:
        await query.answer(
            "Post non trovato.",
            show_alert=True,
        )

        return

    scheduled_post, channel = (
        delivery
    )

    if (
        scheduled_post.status
        != STATUS_PENDING
    ):
        await query.answer(
            "Questo post non è più "
            "modificabile.",
            show_alert=True,
        )

        return

    old_local = to_local_time(
        scheduled_post.run_at
    )

    await state.update_data(
        editing_scheduled_post_id=(
            post_id
        )
    )

    await state.set_state(
        ScheduleStates
        .waiting_reschedule_datetime
    )

    if query.message is not None:
        await query.message.edit_text(
            "🕒 <b>Cambia orario</b>"
            "\n\n"
            f"📢 "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Orario attuale:\n"
            f"<code>"
            f"{old_local.strftime('%d/%m/%Y %H:%M')}"
            f"</code>"
            "\n\n"
            "Invia il nuovo orario:\n"
            "<code>"
            "GG/MM/AAAA HH:MM"
            "</code>",
            reply_markup=(
                reschedule_keyboard(
                    post_id
                )
            ),
        )

    await query.answer()


@router.message(
    ScheduleStates
    .waiting_reschedule_datetime
)
async def receive_reschedule_datetime(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.text:
        await message.answer(
            "❌ Invia data e ora "
            "come testo."
        )

        return

    settings = get_settings()

    data = await state.get_data()

    post_id = data.get(
        "editing_scheduled_post_id"
    )

    if post_id is None:
        await state.clear()

        await message.answer(
            "❌ Sessione scaduta."
        )

        return

    try:
        run_at_local = (
            parse_local_datetime(
                message.text
            )
        )

    except (
        ValueError,
        ZoneInfoNotFoundError,
    ):
        await message.answer(
            "❌ Formato non valido.\n\n"
            "Usa:\n"
            "<code>"
            "GG/MM/AAAA HH:MM"
            "</code>",
            reply_markup=(
                reschedule_keyboard(
                    int(post_id)
                )
            ),
        )

        return

    now_local = datetime.now(
        get_local_timezone()
    )

    if run_at_local <= now_local:
        await message.answer(
            "❌ Il nuovo orario deve "
            "essere nel futuro."
        )

        return

    new_run_at_utc = (
        run_at_local.astimezone(
            timezone.utc
        )
    )

    updated_post = (
        await reschedule_scheduled_post(
            settings.admin_user_id,
            int(post_id),
            new_run_at_utc,
        )
    )

    if updated_post is None:
        await state.clear()

        await message.answer(
            "❌ Il post non è più "
            "modificabile."
        )

        return

    try:
        reschedule_post_job(
            post_id=updated_post.id,
            run_at=updated_post.run_at,
        )

    except RuntimeError:
        # Il DB è già aggiornato.
        #
        # Al prossimo riavvio il job
        # verrà comunque ricaricato.
        await state.clear()

        await message.answer(
            "⚠️ Orario salvato nel DB, "
            "ma lo scheduler non è "
            "disponibile in questo "
            "momento.\n\n"
            "Riavvia il bot."
        )

        return

    delivery = (
        await get_owner_scheduled_post(
            settings.admin_user_id,
            updated_post.id,
        )
    )

    await state.clear()

    if delivery is None:
        await message.answer(
            "✅ Orario aggiornato."
        )

        return

    scheduled_post, channel = (
        delivery
    )

    await message.answer(
        "✅ <b>Orario aggiornato!</b>"
        "\n\n"
        f"📢 "
        f"<b>{escape(channel.title)}</b>"
        "\n"
        f"🗓 "
        f"<b>"
        f"{run_at_local.strftime('%d/%m/%Y')}"
        f"</b>\n"
        f"🕒 "
        f"<b>"
        f"{run_at_local.strftime('%H:%M')}"
        f"</b>",
        reply_markup=(
            scheduled_detail_keyboard(
                scheduled_post.id
            )
        ),
    )
