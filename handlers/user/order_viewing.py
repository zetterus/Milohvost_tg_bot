import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from db import get_user_orders_paginated, count_user_orders
from config import ORDERS_PER_PAGE, ORDER_STATUS_MAP, MAX_PREVIEW_TEXT_LENGTH

from .user_utils import _display_user_main_menu # Импортируем функцию для возврата в главное меню

logger = logging.getLogger(__name__)
router = Router() # Локальный роутер для этого модуля

@router.callback_query(F.data == "view_my_orders")
async def view_my_orders_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает нажатие инлайн-кнопки "Посмотреть мои заказы".
    """
    logger.info(f"Пользователь {callback.from_user.id} нажал 'Посмотреть мои заказы'")
    await _show_user_orders(callback, state, bot, page=0)

async def _show_user_orders(update_object: Message | CallbackQuery, state: FSMContext, bot: Bot, page: int = 0):
    """
    Показывает пользователю его заказы с пагинацией.
    """
    user_id = update_object.from_user.id
    offset = page * ORDERS_PER_PAGE

    user_orders = await get_user_orders_paginated(user_id, offset, ORDERS_PER_PAGE)
    total_orders = await count_user_orders(user_id)
    total_pages = (total_orders + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE  # Вычисляем общее количество страниц

    orders_list_text = f"**Твои заказы (страница {page + 1}/{total_pages if total_pages > 0 else 1}):**\n\n"

    if user_orders:
        for i, order in enumerate(user_orders):
            display_status = ORDER_STATUS_MAP.get(order.status, order.status)
            orders_list_text += (
                f"**Заказ №{order.id}** (Статус: {display_status})\n"
                f"  *Текст:* {order.order_text[:MAX_PREVIEW_TEXT_LENGTH]}{'...' if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH else ''}\n"
                f"  *Дата:* {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            )
            if i < len(user_orders) - 1:
                orders_list_text += "---\n"

        keyboard = InlineKeyboardBuilder()
        if page > 0:
            keyboard.button(text="⬅️ Назад", callback_data=f"my_orders_page:{page - 1}")
        if page < total_pages - 1:
            keyboard.button(text="Вперед ➡️", callback_data=f"my_orders_page:{page + 1}")
        keyboard.adjust(2)

        keyboard.row(InlineKeyboardButton(text="🔙 В главное меню", callback_data="user_main_menu_back"))

        # Всегда редактируем сообщение, так как все входы через CallbackQuery
        await bot.edit_message_text(
            chat_id=update_object.message.chat.id,
            message_id=update_object.message.message_id,
            text=orders_list_text,
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )

    else: # Если заказов нет
        text_no_orders = "У тебя пока нет заказов."
        keyboard_no_orders = InlineKeyboardBuilder()
        keyboard_no_orders.button(text="🔙 В главное меню", callback_data="user_main_menu_back")

        # Всегда редактируем сообщение
        await bot.edit_message_text(
            chat_id=update_object.message.chat.id,
            message_id=update_object.message.message_id,
            text=text_no_orders,
            reply_markup=keyboard_no_orders.as_markup(),
            parse_mode="Markdown"
        )

    await state.update_data(current_orders_page=page)
    if isinstance(update_object, CallbackQuery): # Убеждаемся, что это CallbackQuery перед ответом
        await update_object.answer()

@router.callback_query(F.data.startswith("my_orders_page:"))
async def navigate_my_orders_page(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает нажатия кнопок пагинации для заказов пользователя.
    """
    page = int(callback.data.split(":")[1])
    logger.info(f"Пользователь {callback.from_user.id} перешел на страницу {page} заказов.")
    await _show_user_orders(callback, state, bot, page)