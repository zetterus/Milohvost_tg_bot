"""User order viewing handlers - uses OrderService."""
import logging
import math
import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from core.database import get_db_session
from core.config import settings
from repositories.orders import OrderRepository
from repositories.users import UserRepository
from localization import get_localized_message
logger = logging.getLogger(__name__)
router = Router()
LIMIT = settings.user_orders_per_page
MAX_PREV = settings.max_preview_text_length
async def _show_user_orders(callback: CallbackQuery, lang: str, page: int) -> None:
    user_id = callback.from_user.id
    offset = (page - 1) * LIMIT
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        orders, total = await order_repo.get_user_orders(user_id, offset=offset, limit=LIMIT)
    total_pages = math.ceil(total / LIMIT) if total > 0 else 1
    header = get_localized_message("my_orders_list_title", lang).format(current_page=page, total_pages=total_pages)
    text = header + "\n\n"
    if not orders:
        text += get_localized_message("no_orders_yet", lang)
    else:
        for order in orders:
            preview = order.order_text[:MAX_PREV]
            if len(order.order_text) > MAX_PREV:
                preview += "..."
            text += get_localized_message("order_details_order_id", lang).format(order_id=order.id) + "\n"
            text += get_localized_message("order_details_text", lang).format(preview_text=html.escape(preview)) + "\n"
            text += get_localized_message("order_details_date", lang).format(date=order.created_at.strftime("%d.%m.%Y %H:%M")) + "\n"
            text += get_localized_message("order_divider", lang) + "\n"
    builder = InlineKeyboardBuilder()
    pag = []
    if page > 1:
        pag.append(InlineKeyboardButton(text="⏮️", callback_data="user_orders_page:1"))
        if page > 5:
            pag.append(InlineKeyboardButton(text=get_localized_message("pagination_prev_5", lang), callback_data=f"user_orders_page:{max(1, page-5)}"))
        pag.append(InlineKeyboardButton(text=get_localized_message("pagination_prev", lang), callback_data=f"user_orders_page:{page-1}"))
    if page < total_pages:
        pag.append(InlineKeyboardButton(text=get_localized_message("pagination_next", lang), callback_data=f"user_orders_page:{page+1}"))
        if page < total_pages - 4:
            pag.append(InlineKeyboardButton(text=get_localized_message("pagination_next_5", lang), callback_data=f"user_orders_page:{min(total_pages, page+5)}"))
        pag.append(InlineKeyboardButton(text="⏭️", callback_data=f"user_orders_page:{total_pages}"))
    if pag:
        builder.row(*pag)
    builder.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang), callback_data="user_main_menu_back"))
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode=ParseMode.HTML)
@router.callback_query(F.data == "view_my_orders")
async def view_my_orders(callback: CallbackQuery, lang: str):
    await _show_user_orders(callback, lang, page=1)
@router.callback_query(F.data.startswith("user_orders_page:"))
async def orders_page(callback: CallbackQuery, lang: str):
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    await _show_user_orders(callback, lang, page=page)
