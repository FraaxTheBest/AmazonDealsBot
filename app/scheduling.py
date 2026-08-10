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
from aiogram.exceptions import (
    TelegramAPIError,
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
    create_scheduled_post,
)
from app.scheduler_service import (
    schedule_post_job,
)


router = Router(
    name="scheduling"
)


class ScheduleStates(
    StatesGroup
):
    waiting_datetime = State()


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
        local_timezone = ZoneInfo(
            settings.app_timezone
        )

    except ZoneInfoNotFoundError:
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
            "come testo.\n\n"
            "Esempio:\n"
            "<code>"
            "10/08/2026 09:15"
            "</code>",
            reply_markup=(
                schedule_input_keyboard()
            ),
        )

        return

    settings = get_settings()

    try:
        local_timezone = ZoneInfo(
            settings.app_timezone
        )

    except ZoneInfoNotFoundError:
        await message.answer(
            "❌ Fuso orario "
            "non disponibile."
        )

        return

    try:
        run_at_local = (
            datetime.strptime(
                message.text.strip(),
                "%d/%m/%Y %H:%M",
            )
            .replace(
                tzinfo=local_timezone
            )
        )

    except ValueError:
        await message.answer(
            "❌ Formato non valido.\n\n"
            "Usa esattamente:\n"
            "<code>"
            "GG/MM/AAAA HH:MM"
            "</code>\n\n"
            "Esempio:\n"
            "<code>"
            "10/08/2026 09:15"
            "</code>",
            reply_markup=(
                schedule_input_keyboard()
            ),
        )

        return

    now_local = datetime.now(
        local_timezone
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

    # Snapshot del post.
    #
    # Se successivamente modifichi
    # il template, questo post
    # programmato non cambia.
    post_text = (
        rendered_post
        + "\n\n"
        "⚠️ <i>Dati demo: "
        "provider Amazon reale "
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
            home_keyboard()
        ),
    )
