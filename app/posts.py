from html import escape

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

from app.affiliate import (
    affiliate_admin_text,
    apply_affiliate_link,
)
from app.affiliate_store import get_effective_partner_tag
from app.ai_service import enhance_product_with_ai
from app.amazon.provider_factory import get_product_for_channel
from app.dedupe_store import record_publication
from app.shortlink_service import build_offer_url
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
from app.deal_engine import (
    deal_admin_text,
    evaluate_deal,
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


# =========================================================
# PRODUCT STATE
# =========================================================


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


# =========================================================
# TEMPLATE
# =========================================================


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


# =========================================================
# IMAGES
# =========================================================


def get_available_images(
    product: ProductSnapshot,
) -> list[str]:
    """
    Restituisce:

    PRIMARY
    +
    VARIANTI

    rimuovendo eventuali duplicati.
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
            images.append(
                image
            )

    return images


def get_current_image_index(
    product: ProductSnapshot,
) -> int:
    images = get_available_images(
        product
    )

    if (
        product.image_url
        and product.image_url
        in images
    ):
        return images.index(
            product.image_url
        )

    return 0


# =========================================================
# KEYBOARDS
# =========================================================


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
                text=(
                    "🏠 Menu principale"
                ),
                callback_data=(
                    "menu:home"
                ),
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
                    text=(
                        "Vedi offerta 👀"
                    ),
                    url=get_public_url(
                        product
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "🖼 Cambia immagine"
                    ),
                    callback_data=(
                        "post:image_menu"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 SALVA BOZZA",
                    callback_data="post:save_draft",
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "✅ PUBBLICA ORA"
                    ),
                    callback_data=(
                        "post:publish"
                    ),
                ),
                InlineKeyboardButton(
                    text="🕒 PROGRAMMA",
                    callback_data=(
                        "post:schedule"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ SCARTA",
                    callback_data=(
                        "post:cancel"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        "⬅️ Cambia prodotto"
                    ),
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
    url: str | None = None,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Vedi offerta 👀",
                    url=(url or get_public_url(product)),
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
                    text=(
                        "🏠 Menu principale"
                    ),
                    callback_data=(
                        "menu:home"
                    ),
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


# =========================================================
# TEXT
# =========================================================


def product_preview_text(
    rendered_post: str,
) -> str:
    return (
        "🧪 <b>ANTEPRIMA POST</b>\n"
        "ℹ️ Dati dal provider Amazon configurato."
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

    selected_image = (
        images[index]
    )

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
        "🧪 Per ora la galleria "
        "è DEMO.\n"
        "Con il provider Amazon reale "
        "la prima sarà la foto PRIMARY "
        "del prodotto."
    )


# =========================================================
# TELEGRAM HELPERS
# =========================================================


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
    state: FSMContext,
) -> None:
    """
    Anteprima amministratore.

    Mostra:
    - post finale
    - Affiliate Engine
    - Deal Engine

    Le informazioni tecniche
    NON finiscono nel canale.
    """

    rendered_post = (
        await render_saved_template(
            product
        )
    )

    data = await state.get_data()

    # =====================================================
    # AFFILIATE ENGINE
    # =====================================================

    affiliate_status = data.get(
        "affiliate_status"
    )

    if not affiliate_status:
        affiliate_status = (
            "🔐 <b>Affiliate Engine</b>\n"
            "ℹ️ Stato non disponibile."
        )

    # =====================================================
    # DEAL ENGINE
    # =====================================================

    deal_evaluation = (
        evaluate_deal(
            product
        )
    )

    deal_status = (
        deal_admin_text(
            deal_evaluation
        )
    )

    # Salviamo anche il risultato
    # nell'FSM.
    #
    # Ci tornerà utile nelle
    # prossime fasi dell'Autoposting.
    await state.update_data(
        deal_score=(
            deal_evaluation.score
        ),
        deal_is_valid=(
            deal_evaluation.is_deal
        ),
        deal_verdict=(
            deal_evaluation.verdict
        ),
    )

    # =====================================================
    # ANTEPRIMA ADMIN
    # =====================================================

    preview_text = (
        product_preview_text(
            rendered_post
        )
        + "\n\n"
        "────────────────\n\n"
        + affiliate_status
        + "\n\n"
        "────────────────\n\n"
        + deal_status
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

    index = (
        index % len(images)
    )

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


# =========================================================
# CREA POST
# =========================================================


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


# =========================================================
# SELEZIONE CANALE
# =========================================================


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
        CreatePostStates
        .waiting_product
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
            "🔐 L'Affiliate Engine "
            "controllerà automaticamente "
            "quale link utilizzare.",
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


# =========================================================
# RICEZIONE PRODOTTO
# =========================================================


@router.message(
    CreatePostStates
    .waiting_product
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

    #
    # 1. Recuperiamo prodotto dal provider configurato
    #    usando il canale selezionato.
    #
    settings = get_settings()
    state_data = await state.get_data()
    selected_channel_id = state_data.get("channel_id")
    if selected_channel_id is None:
        await message.answer("❌ Sessione scaduta. Seleziona di nuovo il canale.")
        return

    product = await get_product_for_channel(
        asin=asin,
        owner_telegram_user_id=settings.admin_user_id,
        channel_id=int(selected_channel_id),
    )

    #
    # 2. Affiliate Engine
    #

    product, affiliate_decision = (
        await apply_affiliate_link(
            product=product,
            submitted_value=(
                submitted_value
            ),
            expected_partner_tag=(
                await get_effective_partner_tag(
                    settings.admin_user_id,
                    int(selected_channel_id),
                )
            ),
        )
    )

    #
    # 3. Salviamo prodotto aggiornato
    #
    await save_state_product(
        state,
        product,
    )

    #
    # 4. Salviamo stato affiliate
    #    solo per anteprima admin.
    #
    await state.update_data(
        affiliate_status=(
            affiliate_admin_text(
                affiliate_decision
            )
        )
    )

    #
    # Non aspettiamo più
    # un nuovo prodotto.
    #
    await state.set_state(
        None
    )

    try:
        await send_preview(
            bot=bot,
            chat_id=message.chat.id,
            product=product,
            state=state,
        )

    except TelegramAPIError:
        await message.answer(
            "❌ Non riesco a creare "
            "l'anteprima del post."
        )


# =========================================================
# IMAGE MENU
# =========================================================


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

    #
    # Nessuna immagine Amazon:
    # andiamo direttamente al caricamento.
    #
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


# =========================================================
# NAVIGAZIONE IMMAGINI
# =========================================================


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


# =========================================================
# USA IMMAGINE SELEZIONATA
# =========================================================


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

    index = (
        index % len(images)
    )

    product = (
        product.model_copy(
            update={
                "image_url":
                    images[index]
            }
        )
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
        state=state,
    )

    await query.answer(
        "Immagine selezionata!"
    )


# =========================================================
# IMMAGINE PERSONALIZZATA
# =========================================================


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

    #
    # Telegram invia diverse
    # risoluzioni della stessa foto.
    # Prendiamo la più grande.
    #
    telegram_photo = (
        message.photo[-1]
    )

    product = (
        product.model_copy(
            update={
                "image_url":
                    telegram_photo.file_id
            }
        )
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
        state=state,
    )


# =========================================================
# TORNA DA IMMAGINI
# =========================================================


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
        state=state,
    )

    await query.answer()


# =========================================================
# CAMBIA PRODOTTO
# =========================================================


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
        affiliate_status=None,
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


# =========================================================
# PUBBLICAZIONE
# =========================================================


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

    # AI opzionale: in caso di errore continuiamo con il prodotto originale.
    try:
        ai_result = await enhance_product_with_ai(
            settings.admin_user_id,
            product,
        )
        product = ai_result.product
    except Exception:
        pass

    rendered_post = (
        await render_saved_template(
            product
        )
    )

    #
    # IMPORTANTE:
    #
    # affiliate_status NON viene
    # inserito qui.
    #
    # È informazione solo per
    # l'amministratore.
    #
    post_text = rendered_post
    if settings.amazon_provider == "demo":
        post_text += (
            "\n\n⚠️ <i>Dati demo: provider Amazon reale "
            "non ancora collegato.</i>"
        )

    try:
        public_url = await build_offer_url(
            owner_telegram_user_id=settings.admin_user_id,
            channel_id=channel.id,
            product=product,
        )
    except Exception:
        public_url = get_public_url(product)

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
        sent_message = await send_product_post(
            bot=bot,
            chat_id=(
                channel.telegram_chat_id
            ),
            product=product,
            text=post_text,
            reply_markup=(
                published_keyboard(
                    product,
                    public_url,
                )
            ),
        )

    except TelegramAPIError:
        await query.answer(
            "❌ Pubblicazione fallita.",
            show_alert=True,
        )

        return

    try:
        await record_publication(
            owner_telegram_user_id=settings.admin_user_id,
            channel_id=channel.id,
            product=product,
            source="manual",
            telegram_message_id=sent_message.message_id,
        )
    except Exception:
        pass

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


# =========================================================
# CANCELLA POST
# =========================================================


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
