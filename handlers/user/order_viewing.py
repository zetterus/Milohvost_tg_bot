import logging
import math
import html
from typing import Union

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.enums import ParseMode

from db import get_user_orders_paginated, count_user_orders
from config import USER_ORDERS_PER_PAGE, MAX_PREVIEW_TEXT_LENGTH
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "view_my_orders")
async def view_my_orders_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает нажатие кнопки 'Посмотреть мои заказы'.
    Отображает заказы пользователя с пагинацией.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил просмотр своих заказов.")
    await _show_user_orders(callback, state, lang, current_page=1)


@router.callback_query(F.data.startswith("user_orders_page:"))
async def user_orders_pagination_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает пагинацию для заказов пользователя.
    """
    user_id = callback.from_user.id
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(
            f"Пользователь {user_id}: Неверный формат callback_data для пагинации заказов пользователя: {callback.data}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Пользователь {user_id} переключил страницу заказов на {page}.")
    await _show_user_orders(callback, state, lang, current_page=page)


async def _show_user_orders(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        lang: str,
        current_page: int
):
    """
    Отображает постраничный список активных заказов пользователя.
    """
    user_id = update_object.from_user.id
    offset = (current_page - 1) * USER_ORDERS_PER_PAGE

    orders = await get_user_orders_paginated(
        user_id=user_id,
        offset=offset,
        limit=USER_ORDERS_PER_PAGE
    )
    total_orders = await count_user_orders(user_id=user_id)

    total_pages = math.ceil(total_orders / USER_ORDERS_PER_PAGE) if total_orders > 0 else 1

    header_text = get_localized_message("my_orders_list_title", lang).format(
        current_page=current_page, total_pages=total_pages
    )

    orders_list_text = header_text + "\n\n"

    if not orders:
        orders_list_text += get_localized_message("no_orders_yet", lang)
    else:
        for order in orders:
            preview_text = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
            if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
                preview_text += "..."

            # Предполагается, что объект order имеет атрибуты id, created_at, order_text
            orders_list_text += get_localized_message("order_details_order_id", lang).format(order_id=order.id) + "\n"
            orders_list_text += get_localized_message("order_details_text", lang).format(
                preview_text=html.escape(preview_text)) + "\n"
            orders_list_text += get_localized_message("order_details_date", lang).format(
                date=order.created_at.strftime('%d.%m.%Y %H:%M')) + "\n"
            orders_list_text += get_localized_message("order_divider", lang) + "\n"

    keyboard = InlineKeyboardBuilder()

    # Список для сбора кнопок пагинации
    pagination_buttons = []

    # Кнопки пагинации
    if current_page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⏮️", callback_data="user_orders_page:1"))
        if current_page > 5:
            pagination_buttons.append(InlineKeyboardButton(text=get_localized_message("pagination_prev_5", lang),
                                                           callback_data=f"user_orders_page:{max(1, current_page - 5)}"))
        pagination_buttons.append(InlineKeyboardButton(text=get_localized_message("pagination_prev", lang),
                                                       callback_data=f"user_orders_page:{current_page - 1}"))

    if current_page < total_pages:
        pagination_buttons.append(InlineKeyboardButton(text=get_localized_message("pagination_next", lang),
                                                       callback_data=f"user_orders_page:{current_page + 1}"))
        if current_page < total_pages - 4:
            pagination_buttons.append(InlineKeyboardButton(text=get_localized_message("pagination_next_5", lang),
                                                           callback_data=f"user_orders_page:{min(total_pages, current_page + 5)}"))
        pagination_buttons.append(InlineKeyboardButton(text="⏭️", callback_data=f"user_orders_page:{total_pages}"))

    # Добавляем все кнопки пагинации в один ряд
    if pagination_buttons:  # Добавляем ряд только если есть кнопки пагинации
        keyboard.row(*pagination_buttons)  # <-- ИЗМЕНЕНО: Добавляем все кнопки в один ряд

    # Кнопка возврата в главное меню
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang),
                                      callback_data="user_main_menu_back"))

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(orders_list_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(orders_list_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
