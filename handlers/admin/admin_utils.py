import logging
import math
import urllib.parse

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.utils.markdown import hbold

from config import ORDER_STATUS_MAP, ORDERS_PER_PAGE, MAX_PREVIEW_TEXT_LENGTH
from db import get_all_orders, search_orders
from .admin_filters import IsAdmin

logger = logging.getLogger(__name__)
router = Router()  # Локальный роутер для этого модуля


async def _display_admin_main_menu(update_object: Message | CallbackQuery, state: FSMContext):
    """
    Отображает главное меню админ-панели.
    Принимает Message или CallbackQuery и соответствующим образом отправляет/редактирует сообщение.
    Всегда сбрасывает FSM-состояние.
    """
    await state.clear()  # Очищаем все данные из FSM, чтобы начать с чистого листа

    # Создаем клавиатуру админ-панели
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Просмотреть все заказы 📋", callback_data="admin_all_orders_start")
    keyboard.button(text="Найти заказы 🔍", callback_data="admin_find_orders")
    keyboard.button(text="Управление помощью 💬", callback_data="admin_manage_help_messages")
    keyboard.adjust(1)

    text = hbold("Добро пожаловать в админ-панель! Выберите действие:")
    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(text, reply_markup=reply_markup, parse_mode="HTML")
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")


async def _display_orders_paginated(
        update_object: Message | CallbackQuery,
        state: FSMContext,
        current_page: int,
        is_search: bool = False  # Флаг: это результаты поиска или все заказы
):
    """

    Отображает список заказов с пагинацией в админ-панели.

    Функция может отображать либо все заказы, либо результаты поиска,
    в зависимости от флага 'is_search'. Она динамически формирует текст
    сообщения и клавиатуру для навигации по страницам и просмотра деталей заказов.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение.
    :param state: FSMContext для управления состоянием и данными (например, поисковым запросом).
    :param current_page: Текущий номер отображаемой страницы.
    :param is_search: Булевый флаг, указывающий, является ли текущее отображение результатами поиска.
                     (True для поиска, False для всех заказов).
    :param bot: Экземпляр объекта Bot (желательно для явного вызова методов API).
    """
    user_id = update_object.from_user.id

    offset = (current_page - 1) * ORDERS_PER_PAGE
    # orders: list[Order] = []
    # total_orders: int = 0
    # message_context = ""
    query_text = None

    if is_search:
        data = await state.get_data()
        query_text = data.get("search_query")  # Получаем поисковый запрос из FSM
        if not query_text:
            logger.error(
                f"Админ {user_id}: Попытка пагинации поиска без search_query в FSM. Возврат в админ-панель.")
            text = hbold("Ошибка: поисковый запрос не найден. Начните поиск заново.")
            await _display_admin_main_menu(update_object, state)
            return

        orders, total_orders = await search_orders(search_query=query_text, offset=offset, limit=ORDERS_PER_PAGE)
        message_context = "результатов поиска"

    else:  # Это просмотр всех заказов
        orders, total_orders = await get_all_orders(offset=offset, limit=ORDERS_PER_PAGE)
        message_context = "всех заказов"

    # Обновляем текущую страницу в FSM, это важно для кнопки "Назад к заказам"
    await state.update_data(current_page=current_page)

    total_pages = math.ceil(total_orders / ORDERS_PER_PAGE) if total_orders > 0 else 1

    # --- Текст сообщения ---
    if query_text:
        header_text = hbold(
            f"Результаты поиска по запросу '{query_text}' (Страница {current_page}/{total_pages}, всего: {total_orders}):")
    else:
        header_text = hbold(
            f"Список {message_context} (Страница {current_page}/{total_pages}, всего: {total_orders}):")

    orders_content_text = header_text + "\n\n"

    if not orders:
        orders_content_text += "Заказов на этой странице нет."

    # --- Кнопки заказов ---
    order_buttons_builder = InlineKeyboardBuilder()
    for order in orders:
        display_status = ORDER_STATUS_MAP.get(order.status, order.status)
        preview_text = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
        if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
            preview_text += "..."

        button_text = f"#{order.id} | {preview_text} | {display_status}"
        order_buttons_builder.add(InlineKeyboardButton(
            text=button_text,
            callback_data=f"view_order_{order.id}"
        ))
    order_buttons_builder.adjust(1)

    # --- Кнопки пагинации ---
    pagination_builder = InlineKeyboardBuilder()

    page_base_prefix = "admin_search_page" if is_search else "admin_all_orders_page"
    encoded_query_text = urllib.parse.quote_plus(query_text) if query_text else ""

    if current_page > 1:
        pagination_builder.button(text="⏮️", callback_data=f"{page_base_prefix}:{1}:{encoded_query_text}")
        if current_page > 5:
            pagination_builder.button(text="◀️5",
                                      callback_data=f"{page_base_prefix}:{max(1, current_page - 5)}:{encoded_query_text}")
        pagination_builder.button(text="◀️",
                                  callback_data=f"{page_base_prefix}:{current_page - 1}:{encoded_query_text}")

    if current_page < total_pages:
        pagination_builder.button(text="▶️",
                                  callback_data=f"{page_base_prefix}:{current_page + 1}:{encoded_query_text}")
        if current_page < total_pages - 4:
            pagination_builder.button(text="▶️5",
                                      callback_data=f"{page_base_prefix}:{min(total_pages, current_page + 5)}:{encoded_query_text}")
        pagination_builder.button(text="⏭️",
                                  callback_data=f"{page_base_prefix}:{total_pages}:{encoded_query_text}")

    # Комбинируем клавиатуры
    final_keyboard = InlineKeyboardBuilder()
    final_keyboard.attach(order_buttons_builder)

    if total_orders > ORDERS_PER_PAGE:
        final_keyboard.row(*pagination_builder.buttons)  # Добавляем кнопки пагинации в один ряд

    final_keyboard.row(InlineKeyboardButton(
        text="🔙 В админ-панель",
        callback_data="admin_panel_back"
    ))

    # Отправляем/редактируем сообщение
    if isinstance(update_object, Message):
        await update_object.answer(orders_content_text, reply_markup=final_keyboard.as_markup(), parse_mode="HTML")
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(orders_content_text, reply_markup=final_keyboard.as_markup(),
                                              parse_mode="HTML")
