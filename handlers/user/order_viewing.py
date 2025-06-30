import logging
from typing import Union

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode # Явный импорт ParseMode

from db import get_user_orders_paginated, count_user_orders
from config import ORDERS_PER_PAGE, ORDER_STATUS_MAP, MAX_PREVIEW_TEXT_LENGTH

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "view_my_orders")
async def view_my_orders_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает нажатие инлайн-кнопки "Посмотреть мои заказы".
    Переводит пользователя на первую страницу его заказов.
    """
    logger.info(f"Пользователь {callback.from_user.id} нажал 'Посмотреть мои заказы'.")
    # Передаем CallbackQuery напрямую, так как это начальная точка входа из Inline-кнопки
    await _show_user_orders(callback, state, bot, page=0)


async def _show_user_orders(update_object: Union[Message, CallbackQuery], state: FSMContext, bot: Bot, page: int = 0):
    """
    Показывает пользователю его заказы с пагинацией.
    Редактирует или отправляет сообщение в зависимости от типа update_object,
    используя предоставленный объект `bot`.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение.
    :param state: FSMContext для управления состоянием.
    :param bot: Экземпляр объекта Bot (обязательно для отправки/редактирования сообщений).
    :param page: Текущий номер отображаемой страницы (начинается с 0).
    """
    user_id = update_object.from_user.id
    chat_id = update_object.message.chat.id if isinstance(update_object, CallbackQuery) else update_object.chat.id
    message_id = update_object.message.message_id if isinstance(update_object, CallbackQuery) else update_object.message_id

    offset = page * ORDERS_PER_PAGE

    user_orders = await get_user_orders_paginated(user_id, offset, ORDERS_PER_PAGE)
    total_orders = await count_user_orders(user_id)
    # Вычисляем общее количество страниц, минимум 1, чтобы избежать деления на ноль и отображения 0/0
    total_pages = (total_orders + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE if total_orders > 0 else 1

    orders_list_text = f"**Твои заказы (страница {page + 1}/{total_pages}):**\n\n"
    keyboard = InlineKeyboardBuilder()

    if user_orders:
        for i, order in enumerate(user_orders):
            display_status = ORDER_STATUS_MAP.get(order.status, order.status)
            # Обрезаем текст заказа для предпросмотра
            preview_text = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
            if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
                preview_text += "..."

            orders_list_text += (
                f"**Заказ №{order.id}** (Статус: {display_status})\n"
                f"  *Текст:* {preview_text}\n"
                f"  *Дата:* {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            )
            if i < len(user_orders) - 1:
                orders_list_text += "---\n" # Разделитель между заказами

        # Кнопки пагинации
        if page > 0:
            keyboard.button(text="⬅️ Назад", callback_data=f"my_orders_page:{page - 1}")
        if page < total_pages - 1:
            keyboard.button(text="Вперед ➡️", callback_data=f"my_orders_page:{page + 1}")
        keyboard.adjust(2) # Размещаем кнопки назад/вперед в одном ряду

    else: # Если заказов нет
        orders_list_text = "У тебя пока нет заказов."

    # Кнопка "В главное меню" всегда присутствует
    keyboard.row(InlineKeyboardButton(text="🔙 В главное меню", callback_data="user_main_menu_back"))

    reply_markup = keyboard.as_markup()

    # Отправляем или редактируем сообщение в зависимости от типа update_object
    if isinstance(update_object, Message):
        await bot.send_message(
            chat_id=chat_id,
            text=orders_list_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    elif isinstance(update_object, CallbackQuery):
        # Отвечаем на CallbackQuery перед редактированием, чтобы убрать "часики"
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=orders_list_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        await update_object.answer() # Отвечаем на callback

    await state.update_data(current_orders_page=page)


@router.callback_query(F.data.startswith("my_orders_page:"))
async def navigate_my_orders_page(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает нажатия кнопок пагинации для заказов пользователя.
    """
    page = int(callback.data.split(":")[1])
    logger.info(f"Пользователь {callback.from_user.id} перешел на страницу {page} заказов.")
    await _show_user_orders(callback, state, bot, page)