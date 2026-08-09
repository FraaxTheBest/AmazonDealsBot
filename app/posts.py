from html import escape
from urllib.parse import urlparse

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import (
    State,
    StatesGroup,
)
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from app.amazon.models import (
    ProductSnapshot,
)
from app.amazon.provider import (
    MockAmazonProvider,
)
from app.amazon.utils import extract_asin
from app.config import get_settings
from app.database import (
    Channel,
    get_channel,
    list_channels,
)
from app.publisher import (
    PHOTO_CAPTION_LIMIT,
    send_product_post,
)
from app.template_engine import (
    DEFAULT_POST_TEMPLATE,
    get_public_url,
    render_template,
)
from app.template_store import (
    get_default_template_content,
)


router = Router(
    name="posts"
)

amazon_provider = (
    MockAmazonProvider()
)


class CreatePostStates(
    StatesGroup
):
    waiting_product = State()

    waiting_custom_image = State()


async def get_state_product(
    state: FSMContext,
) -> ProductSnapshot | None:
    data = await state.get_data()

    product_data = data.get(
        "product"
    )

    if product_data is None:
        return None

    return ProductSnapshot.model_validate(
        product_data
    )


async def save_state_product(
    state: FSMContext,
    product: ProductSnapshot,
) -> None:
    await state.update_data(
        product=product.model_dump(
            mode="json"
        )
    )


async def render_saved_template(
    product: ProductSnapshot,
) -> str:
    settings = get_settings()

    content = (
        await get_default_template_content(
            settings.admin_user_id,
            DEFAULT_POST_TEMPLATE,
        )
    )

    try:
        return render_template(
            content,
            product,
        )

    except ValueError:
        return render_template(
            DEFAULT_POST_TEMPLATE,
            product,
        )


def is_amzn_short_url(
    value: str,
) -> bool:
    try:
        parsed = urlparse(
            value.strip()
        )

    except ValueError:
        return False

    hostname = (
        parsed.hostname.lower()
        if parsed.hostname
        else ""
    )

    return (
        parsed.scheme
        in {
            "http",
            "https",
        }
        and hostname
        in {
            "amzn.to",
            "www.amzn.to",
        }
    )


def get_available_images(
    product: ProductSnapshot,
) -> list[str]:
    """
    Restituisce:
    PRIMARY + VARIANTI.

    Rimuove eventuali duplicati.
    """

    images: list[str] = []

    candidates = [
        product.primary_image_url,
        *product.variant_image_urls,
    ]

    for image in candidates:
        if (
            image
            and image not in images
        ):
            images.append(image)

    return images


def get_current_image_index(
    product: ProductSnapshot,
) -> int:
    images = get_available_images(
        product
    )

    if (
        product.image_url
        and product.image_url in images
    ):
        return images.index(
            product.image_url
        )

    return 0


def channel_selection_keyboard(
    channels: list[Channel],
) -> InlineKeyboardMarkup:
    rows = []

    for channel in channels:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"📢 "
                        f"{channel.title[:35]}"
                    ),
                    callback_data=(
                        f"post:channel:"
                        f"{channel.id}"
                    ),
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text="🏠 Menu principale",
                callback_data="menu:home",
            )
        ]
    )

    return InlineKeyboardMarkup(
        inline_keyboard=rows
    )


def product_input_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Indietro",
                    callback_data=(
                        "post:back_channels"
                    ),
                ),
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data=(
                        "menu:home"
                    ),
                ),
            ]
        ]
    )


def preview_keyboard(
    product: ProductSnapshot,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Vedi offerta 👀",
                    url=get_public_url(
                        product
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🖼 Cambia immagine",
                    callback_data=(
                        "post:image_menu"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ PUBBLICA",
                    callback_data=(
                        "post:publish"
                    ),
                ),
                InlineKeyboardButton(
                    text="❌ SCARTA",
                    callback_data=(
                        "post:cancel"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Cambia prodotto",
                    callback_data=(
                        "post:retry_product"
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


def published_keyboard(
    product: ProductSnapshot,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Vedi offerta 👀",
                    url=get_public_url(
                        product
                    ),
                )
            ]
        ]
    )


def home_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Menu principale",
                    callback_data="menu:home",
                )
            ]
        ]
    )


def image_picker_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️",
                    callback_data=(
                        "post:image_prev"
                    ),
                ),
                InlineKeyboardButton(
                    text="✅ Usa questa",
                    callback_data=(
                        "post:image_use"
                    ),
                ),
                InlineKeyboardButton(
                    text="➡️",
                    callback_data=(
                        "post:image_next"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "📤 Carica immagine tua"
                    ),
                    callback_data=(
                        "post:image_custom"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "↩️ Torna all'anteprima"
                    ),
                    callback_data=(
                        "post:image_back"
                    ),
                )
            ],
        ]
    )


def custom_image_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=(
                        "↩️ Torna all'anteprima"
                    ),
                    callback_data=(
                        "post:image_back"
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


def product_preview_text(
    rendered_post: str,
) -> str:
    return (
        "🧪 <b>ANTEPRIMA POST</b>\n"
        "⚠️ Dati prodotto ancora MOCK."
        "\n\n"
        "────────────────\n\n"
        f"{rendered_post}"
    )


def image_picker_caption(
    product: ProductSnapshot,
    index: int,
) -> str:
    images = get_available_images(
        product
    )

    total = len(images)

    if total == 0:
        return (
            "🖼 <b>Immagini</b>\n\n"
            "Nessuna immagine disponibile."
        )

    selected_image = images[
        index
    ]

    if (
        selected_image
        == product.primary_image_url
    ):
        image_type = (
            "⭐ Immagine principale "
            "(PRIMARY)"
        )

    else:
        image_type = (
            "🖼 Immagine alternativa"
        )

    return (
        "🖼 <b>Scegli immagine</b>\n\n"
        f"{image_type}\n"
        f"Immagine {index + 1} "
        f"di {total}\n\n"
        "🧪 Per ora la galleria è DEMO.\n"
        "Con il provider Amazon reale "
        "la prima sarà la foto PRIMARY "
        "del prodotto."
    )


async def delete_message_safely(
    message: Message | None,
) -> None:
    if message is None:
        return

    try:
        await message.delete()

    except TelegramAPIError:
        pass


async def send_preview(
    bot: Bot,
    chat_id: int,
    product: ProductSnapshot,
) -> None:
    rendered_post = (
        await render_saved_template(
            product
        )
    )

    preview_text = (
        product_preview_text(
            rendered_post
        )
    )

    await send_product_post(
        bot=bot,
        chat_id=chat_id,
        product=product,
        text=preview_text,
        reply_markup=(
            preview_keyboard(
                product
            )
        ),
    )


async def send_image_picker(
    bot: Bot,
    chat_id: int,
    product: ProductSnapshot,
    index: int,
) -> None:
    images = get_available_images(
        product
    )

    if not images:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "🖼 <b>Nessuna immagine "
                "disponibile.</b>\n\n"
                "Puoi comunque caricare "
                "una tua immagine."
            ),
            reply_markup=(
                custom_image_keyboard()
            ),
        )
        return

    index = index % len(images)

    await bot.send_photo(
        chat_id=chat_id,
        photo=images[index],
        caption=(
            image_picker_caption(
                product,
                index,
            )
        ),
        reply_markup=(
            image_picker_keyboard()
        ),
    )


@router.callback_query(
    F.data == "menu:create_post"
)
async def create_post_start(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    await state.clear()

    channels = await list_channels(
        settings.admin_user_id
    )

    if not channels:
        await query.answer(
            "Prima devi collegare "
            "almeno un canale.",
            show_alert=True,
        )
        return

    if query.message is not None:
        await query.message.edit_text(
            "➕ <b>Crea Post</b>\n\n"
            "Scegli il canale in cui "
            "pubblicare:",
            reply_markup=(
                channel_selection_keyboard(
                    channels
                )
            ),
        )

    await query.answer()


@router.callback_query(
    F.data.startswith(
        "post:channel:"
    )
)
async def select_post_channel(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    if query.data is None:
        return

    channel_id = int(
        query.data.split(":")[-1]
    )

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

    await state.update_data(
        channel_id=channel.id
    )

    await state.set_state(
        CreatePostStates.waiting_product
    )

    if query.message is not None:
        await query.message.edit_text(
            "🔗 <b>Inserisci prodotto</b>"
            "\n\n"
            f"Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Puoi inviare:\n\n"
            "• URL Amazon.it\n"
            "• link corto amzn.to\n"
            "• direttamente l'ASIN\n\n"
            "Se inserisci un link "
            "<b>amzn.to</b>, il bot "
            "manterrà quel link corto.",
            reply_markup=(
                product_input_keyboard()
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "post:back_channels"
)
async def back_to_channel_selection(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    await state.clear()

    channels = await list_channels(
        settings.admin_user_id
    )

    if query.message is not None:
        await query.message.edit_text(
            "➕ <b>Crea Post</b>\n\n"
            "Scegli il canale in cui "
            "pubblicare:",
            reply_markup=(
                channel_selection_keyboard(
                    channels
                )
            ),
        )

    await query.answer()


@router.message(
    CreatePostStates.waiting_product
)
async def receive_product(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    if not message.text:
        await message.answer(
            "❌ Invia un URL Amazon.it, "
            "un link amzn.to oppure "
            "un ASIN.",
            reply_markup=(
                product_input_keyboard()
            ),
        )
        return

    submitted_value = (
        message.text.strip()
    )

    asin = await extract_asin(
        submitted_value
    )

    if asin is None:
        await message.answer(
            "❌ Non riesco a trovare "
            "un ASIN valido.\n\n"
            "Puoi utilizzare:\n"
            "• link Amazon.it\n"
            "• link amzn.to\n"
            "• ASIN di 10 caratteri",
            reply_markup=(
                product_input_keyboard()
            ),
        )
        return

    product = (
        await amazon_provider.get_product(
            asin
        )
    )

    if is_amzn_short_url(
        submitted_value
    ):
        product = product.model_copy(
            update={
                "affiliate_short_url":
                    submitted_value
            }
        )

    await save_state_product(
        state,
        product,
    )

    # Finito l'inserimento prodotto.
    # Manteniamo i dati FSM ma non
    # aspettiamo più un nuovo link.
    await state.set_state(
        None
    )

    try:
        await send_preview(
            bot=bot,
            chat_id=message.chat.id,
            product=product,
        )

    except TelegramAPIError:
        await message.answer(
            "❌ Non riesco a creare "
            "l'anteprima del post."
        )


@router.callback_query(
    F.data == "post:image_menu"
)
async def open_image_menu(
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

    images = get_available_images(
        product
    )

    if not images:
        await delete_message_safely(
            query.message
        )

        await state.set_state(
            CreatePostStates
            .waiting_custom_image
        )

        await bot.send_message(
            chat_id=query.from_user.id,
            text=(
                "📤 <b>Carica "
                "un'immagine</b>\n\n"
                "Inviami la foto che vuoi "
                "usare per questo post."
            ),
            reply_markup=(
                custom_image_keyboard()
            ),
        )

        await query.answer()
        return

    index = get_current_image_index(
        product
    )

    await state.update_data(
        image_index=index
    )

    await delete_message_safely(
        query.message
    )

    try:
        await send_image_picker(
            bot=bot,
            chat_id=query.from_user.id,
            product=product,
            index=index,
        )

    except TelegramAPIError:
        await bot.send_message(
            chat_id=query.from_user.id,
            text=(
                "❌ Non riesco a caricare "
                "la galleria demo.\n\n"
                "Puoi comunque caricare "
                "una tua immagine."
            ),
            reply_markup=(
                custom_image_keyboard()
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "post:image_prev"
)
@router.callback_query(
    F.data == "post:image_next"
)
async def browse_images(
    query: CallbackQuery,
    state: FSMContext,
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

    images = get_available_images(
        product
    )

    if not images:
        await query.answer(
            "Nessuna immagine.",
            show_alert=True,
        )
        return

    data = await state.get_data()

    index = int(
        data.get(
            "image_index",
            0,
        )
    )

    if (
        query.data
        == "post:image_next"
    ):
        index = (
            index + 1
        ) % len(images)

    else:
        index = (
            index - 1
        ) % len(images)

    await state.update_data(
        image_index=index
    )

    if query.message is not None:
        try:
            await query.message.edit_media(
                media=InputMediaPhoto(
                    media=images[index],
                    caption=(
                        image_picker_caption(
                            product,
                            index,
                        )
                    ),
                    parse_mode=(
                        ParseMode.HTML
                    ),
                ),
                reply_markup=(
                    image_picker_keyboard()
                ),
            )

        except TelegramAPIError:
            await query.answer(
                "❌ Impossibile caricare "
                "questa immagine.",
                show_alert=True,
            )
            return

    await query.answer()


@router.callback_query(
    F.data == "post:image_use"
)
async def use_selected_image(
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

    images = get_available_images(
        product
    )

    if not images:
        await query.answer(
            "Nessuna immagine.",
            show_alert=True,
        )
        return

    data = await state.get_data()

    index = int(
        data.get(
            "image_index",
            0,
        )
    )

    index = index % len(images)

    product = product.model_copy(
        update={
            "image_url":
                images[index]
        }
    )

    await save_state_product(
        state,
        product,
    )

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
    )

    await query.answer(
        "Immagine selezionata!"
    )


@router.callback_query(
    F.data == "post:image_custom"
)
async def custom_image_start(
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
        CreatePostStates
        .waiting_custom_image
    )

    await delete_message_safely(
        query.message
    )

    await bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "📤 <b>Carica immagine "
            "personalizzata</b>\n\n"
            "Mandami adesso una foto.\n\n"
            "Verrà usata solamente per "
            "questo post."
        ),
        reply_markup=(
            custom_image_keyboard()
        ),
    )

    await query.answer()


@router.message(
    CreatePostStates
    .waiting_custom_image
)
async def receive_custom_image(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    if not message.photo:
        await message.answer(
            "❌ Devi inviarmi una "
            "foto vera.\n\n"
            "Usa 📎 e scegli Foto.",
            reply_markup=(
                custom_image_keyboard()
            ),
        )
        return

    product = (
        await get_state_product(
            state
        )
    )

    if product is None:
        await state.clear()

        await message.answer(
            "❌ Sessione scaduta.\n"
            "Ricomincia da /start."
        )
        return

    # Prendiamo la versione più grande
    # ricevuta da Telegram.
    telegram_photo = (
        message.photo[-1]
    )

    product = product.model_copy(
        update={
            "image_url":
                telegram_photo.file_id
        }
    )

    await save_state_product(
        state,
        product,
    )

    await state.set_state(
        None
    )

    await message.answer(
        "✅ Immagine personalizzata "
        "selezionata."
    )

    await send_preview(
        bot=bot,
        chat_id=message.chat.id,
        product=product,
    )


@router.callback_query(
    F.data == "post:image_back"
)
async def back_from_images(
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
    )

    await query.answer()


@router.callback_query(
    F.data == "post:retry_product"
)
async def retry_product(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()

    channel_id = data.get(
        "channel_id"
    )

    if channel_id is None:
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

    await state.update_data(
        product=None,
        image_index=0,
    )

    await state.set_state(
        CreatePostStates
        .waiting_product
    )

    await delete_message_safely(
        query.message
    )

    await bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "🔗 <b>Inserisci "
            "prodotto</b>\n\n"
            f"Canale: "
            f"<b>{escape(channel.title)}</b>"
            "\n\n"
            "Incolla un nuovo URL "
            "Amazon.it, un link amzn.to "
            "oppure l'ASIN."
        ),
        reply_markup=(
            product_input_keyboard()
        ),
    )

    await query.answer()


@router.callback_query(
    F.data == "post:publish"
)
async def publish_post(
    query: CallbackQuery,
    bot: Bot,
    state: FSMContext,
) -> None:
    settings = get_settings()

    data = await state.get_data()

    channel_id = data.get(
        "channel_id"
    )

    product = (
        await get_state_product(
            state
        )
    )

    if (
        channel_id is None
        or product is None
    ):
        await query.answer(
            "Sessione scaduta. "
            "Ricomincia da Crea Post.",
            show_alert=True,
        )

        await state.clear()
        return

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

    rendered_post = (
        await render_saved_template(
            product
        )
    )

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
        await query.answer(
            "Il template è troppo "
            "lungo per essere usato "
            "come caption della foto.",
            show_alert=True,
        )
        return

    try:
        await send_product_post(
            bot=bot,
            chat_id=(
                channel.telegram_chat_id
            ),
            product=product,
            text=post_text,
            reply_markup=(
                published_keyboard(
                    product
                )
            ),
        )

    except TelegramAPIError:
        await query.answer(
            "❌ Pubblicazione fallita.",
            show_alert=True,
        )
        return

    await state.clear()

    await delete_message_safely(
        query.message
    )

    await bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "✅ <b>Post "
            "pubblicato!</b>\n\n"
            f"📢 Canale: "
            f"<b>{escape(channel.title)}</b>"
        ),
        reply_markup=(
            home_keyboard()
        ),
    )

    await query.answer(
        "Pubblicato!"
    )


@router.callback_query(
    F.data == "post:cancel"
)
async def cancel_post(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
) -> None:
    await state.clear()

    await delete_message_safely(
        query.message
    )

    await bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "❌ Creazione post "
            "annullata."
        ),
        reply_markup=(
            home_keyboard()
        ),
    )

    await query.answer()
