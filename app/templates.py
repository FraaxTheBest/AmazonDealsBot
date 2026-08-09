from decimal import Decimal
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)

from app.amazon.models import ProductSnapshot
from app.config import get_settings
from app.template_engine import (
    DEFAULT_POST_TEMPLATE,
    render_template,
)
from app.template_store import (
    get_default_template_content,
    reset_default_template,
    save_default_template,
)


router = Router(
    name="templates"
)


class TemplateStates(StatesGroup):
    waiting_content = State()


SAMPLE_PRODUCT = ProductSnapshot(
    asin="B00DEMO123",
    title=(
        "Prodotto Amazon di esempio "
        "per anteprima template"
    ),
    detail_url=(
        "https://www.amazon.it/dp/"
        "B00DEMO123"
    ),
    affiliate_url=(
        "https://www.amazon.it/dp/"
        "B00DEMO123?tag=example-21"
    ),
    affiliate_short_url=(
        "https://amzn.to/esempio"
    ),
    brand="Amazon Demo",
    current_price=Decimal("34.99"),
    original_price=Decimal("49.99"),
    discount_percentage=Decimal("30"),
    rating=Decimal("4.7"),
    reviews_count=1256,
    availability="Disponibile",
    seller="Amazon",
    ships_from="Amazon",
)


def template_menu_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✏️ Modifica",
                    callback_data=(
                        "template:edit"
                    ),
                ),
                InlineKeyboardButton(
                    text="👁 Anteprima",
                    callback_data=(
                        "template:preview"
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="♻️ Ripristina default",
                    callback_data=(
                        "template:reset"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Menu principale",
                    callback_data="menu:home",
                )
            ],
        ]
    )


def template_editor_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ Annulla modifica",
                    callback_data=(
                        "template:menu"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="menu:home",
                )
            ],
        ]
    )


def template_back_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Template",
                    callback_data=(
                        "template:menu"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Home",
                    callback_data="menu:home",
                )
            ],
        ]
    )


def reset_confirmation_keyboard(
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Sì, ripristina",
                    callback_data=(
                        "template:reset_yes"
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ No",
                    callback_data=(
                        "template:menu"
                    ),
                )
            ],
        ]
    )


def template_menu_text(
    content: str,
) -> str:
    safe_content = escape(
        content
    )

    return (
        "📝 <b>Template Post</b>\n\n"
        "Questo è il template "
        "attualmente utilizzato "
        "per i post:\n\n"
        f"<pre>{safe_content}</pre>\n\n"
        "Puoi modificarlo, vedere "
        "un'anteprima oppure "
        "ripristinare quello originale."
    )


async def show_template_menu(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    await state.clear()

    content = (
        await get_default_template_content(
            settings.admin_user_id,
            DEFAULT_POST_TEMPLATE,
        )
    )

    if query.message is not None:
        await query.message.edit_text(
            template_menu_text(
                content
            ),
            reply_markup=(
                template_menu_keyboard()
            ),
            link_preview_options=(
                LinkPreviewOptions(
                    is_disabled=True
                )
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "menu:templates"
)
async def template_menu(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await show_template_menu(
        query,
        state,
    )


@router.callback_query(
    F.data == "template:menu"
)
async def template_menu_back(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await show_template_menu(
        query,
        state,
    )


@router.callback_query(
    F.data == "template:edit"
)
async def edit_template(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(
        TemplateStates.waiting_content
    )

    if query.message is not None:
        await query.message.edit_text(
            "✏️ <b>Modifica Template</b>\n\n"
            "Inviami adesso il nuovo "
            "template come messaggio.\n\n"

            "<b>Placeholder semplici:</b>\n"
            "<code>{title}</code>\n"
            "<code>{brand}</code>\n"
            "<code>{asin}</code>\n"
            "<code>{price}</code>\n"
            "<code>{original_price}</code>\n"
            "<code>{discount}</code>\n"
            "<code>{link}</code>\n"
            "<code>{rating}</code>\n"
            "<code>{reviews}</code>\n"
            "<code>{availability}</code>\n"
            "<code>{seller}</code>\n"
            "<code>{ships_from}</code>\n\n"

            "<b>Placeholder intelligenti:</b>\n"
            "<code>{price_line}</code>\n"
            "<code>{rating_line}</code>\n"
            "<code>{shipping_line}</code>\n\n"

            "💡 Ti consiglio soprattutto "
            "quelli intelligenti perché "
            "gestiscono automaticamente "
            "i dati mancanti.\n\n"

            "Puoi usare emoji e la "
            "formattazione HTML Telegram "
            "come <code>&lt;b&gt;</code>, "
            "<code>&lt;i&gt;</code> e "
            "<code>&lt;s&gt;</code>.",
            reply_markup=(
                template_editor_keyboard()
            ),
        )

    await query.answer()


@router.message(
    TemplateStates.waiting_content
)
async def receive_template(
    message: Message,
    state: FSMContext,
) -> None:
    if not message.text:
        await message.answer(
            "❌ Il template deve essere "
            "un messaggio di testo.",
            reply_markup=(
                template_editor_keyboard()
            ),
        )
        return

    content = message.text.strip()

    if not content:
        await message.answer(
            "❌ Il template non può "
            "essere vuoto."
        )
        return

    if len(content) > 2500:
        await message.answer(
            "❌ Template troppo lungo.\n\n"
            "Mantienilo sotto i "
            "2500 caratteri."
        )
        return

    try:
        rendered = render_template(
            content,
            SAMPLE_PRODUCT,
        )

    except ValueError as exc:
        await message.answer(
            "❌ <b>Template non valido</b>"
            "\n\n"
            f"{escape(str(exc))}\n\n"
            "Controlla i placeholder "
            "e riprova.",
            reply_markup=(
                template_editor_keyboard()
            ),
        )
        return

    if len(rendered) > 3500:
        await message.answer(
            "❌ Il risultato del template "
            "è troppo lungo per Telegram."
        )
        return

    # Prima proviamo davvero a farlo
    # interpretare a Telegram.
    # Così intercettiamo anche HTML
    # scritto male prima del salvataggio.
    try:
        preview_message = (
            await message.answer(
                "👁 <b>Anteprima nuovo "
                "template</b>\n\n"
                f"{rendered}",
                link_preview_options=(
                    LinkPreviewOptions(
                        is_disabled=True
                    )
                ),
            )
        )

    except TelegramAPIError:
        await message.answer(
            "❌ Il testo contiene "
            "formattazione HTML non "
            "valida.\n\n"
            "Controlla tag come "
            "<code>&lt;b&gt;</code>, "
            "<code>&lt;i&gt;</code> "
            "e <code>&lt;s&gt;</code> "
            "e riprova.",
            reply_markup=(
                template_editor_keyboard()
            ),
        )
        return

    settings = get_settings()

    await save_default_template(
        owner_telegram_user_id=(
            settings.admin_user_id
        ),
        content=content,
        default_content=(
            DEFAULT_POST_TEMPLATE
        ),
    )

    await state.clear()

    await preview_message.edit_text(
        "✅ <b>Template salvato!</b>\n\n"
        "👁 <b>Anteprima:</b>\n\n"
        f"{rendered}",
        reply_markup=(
            template_back_keyboard()
        ),
        link_preview_options=(
            LinkPreviewOptions(
                is_disabled=True
            )
        ),
    )


@router.callback_query(
    F.data == "template:preview"
)
async def preview_template(
    query: CallbackQuery,
) -> None:
    settings = get_settings()

    content = (
        await get_default_template_content(
            settings.admin_user_id,
            DEFAULT_POST_TEMPLATE,
        )
    )

    try:
        rendered = render_template(
            content,
            SAMPLE_PRODUCT,
        )

    except ValueError:
        await query.answer(
            "Template non valido. "
            "Modificalo o ripristinalo.",
            show_alert=True,
        )
        return

    if query.message is not None:
        try:
            await query.message.edit_text(
                "👁 <b>Anteprima Template</b>"
                "\n\n"
                "🧪 Dati di esempio:\n\n"
                f"{rendered}",
                reply_markup=(
                    template_back_keyboard()
                ),
                link_preview_options=(
                    LinkPreviewOptions(
                        is_disabled=True
                    )
                ),
            )

        except TelegramAPIError:
            await query.answer(
                "Il template contiene "
                "HTML non valido.",
                show_alert=True,
            )
            return

    await query.answer()


@router.callback_query(
    F.data == "template:reset"
)
async def reset_template_question(
    query: CallbackQuery,
) -> None:
    if query.message is not None:
        await query.message.edit_text(
            "♻️ <b>Ripristinare il "
            "template?</b>\n\n"
            "Il template personalizzato "
            "verrà sostituito da quello "
            "originale.",
            reply_markup=(
                reset_confirmation_keyboard()
            ),
        )

    await query.answer()


@router.callback_query(
    F.data == "template:reset_yes"
)
async def reset_template_confirmed(
    query: CallbackQuery,
    state: FSMContext,
) -> None:
    settings = get_settings()

    await reset_default_template(
        owner_telegram_user_id=(
            settings.admin_user_id
        ),
        default_content=(
            DEFAULT_POST_TEMPLATE
        ),
    )

    await state.clear()

    if query.message is not None:
        await query.message.edit_text(
            "✅ <b>Template ripristinato!"
            "</b>\n\n"
            "È stato riattivato il "
            "template originale.",
            reply_markup=(
                template_back_keyboard()
            ),
        )

    await query.answer(
        "Template ripristinato!"
    )
