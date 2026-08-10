from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.config import get_settings
from app.drafts_store import create_draft
from app.posts import get_state_product, render_saved_template


router = Router(name="post_draft_bridge")


@router.callback_query(F.data == "post:save_draft")
async def save_manual_draft(query: CallbackQuery, state: FSMContext) -> None:
    settings = get_settings()
    data = await state.get_data()
    channel_id = data.get("channel_id")
    product = await get_state_product(state)
    if channel_id is None or product is None:
        await query.answer("Sessione scaduta.", show_alert=True)
        return

    text = await render_saved_template(product)
    draft = await create_draft(
        settings.admin_user_id,
        int(channel_id),
        product,
        text,
        source="manual",
    )
    await query.answer(f"Bozza #{draft.id} salvata.", show_alert=True)
