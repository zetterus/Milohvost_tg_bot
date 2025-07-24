import logging
import math
import urllib.parse
from typing import Union

from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.enums import ParseMode

from config import ORDERS_PER_PAGE, MAX_PREVIEW_TEXT_LENGTH
from db import get_all_orders, search_orders
from localization import get_localized_message

logger = logging.getLogger(__name__)


# Функция для создания клавиатуры главного меню админ-панели
def _get_admin_main_menu_keyboard(lang: str) -> InlineKeyboardBuilder:
    """
    Создает инлайн-клавиатуру для главного меню админ-панели, используя локализованные тексты.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=get_localized_message("admin_button_all_orders", lang), callback_data="admin_all_orders_start")
    builder.button(text=get_localized_message("admin_button_find_orders", lang), callback_data="admin_find_orders")
    builder.button(text=get_localized_message("admin_button_manage_help", lang),
                   callback_data="admin_manage_help_messages")
    builder.adjust(1)
    return builder


async def _display_admin_main_menu(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        lang: str
):
    """
    Отображает главное меню админ-панели.
    Принимает Message или CallbackQuery и соответствующим образом отправляет/редактирует сообщение.
    Всегда сбрасывает FSM-состояние.
    Использует локализацию, получая язык из аргумента lang.
    """
    user_id = update_object.from_user.id
    logger.info(
        f"Админ {user_id} переходит в главное меню админ-панели (язык: {lang}).")

    await state.clear()

    # Используем новую внутреннюю функцию для создания клавиатуры
    keyboard = _get_admin_main_menu_keyboard(lang)
    reply_markup = keyboard.as_markup()

    # Локализованный текст приветствия/меню
    text = get_localized_message("admin_welcome_message", lang)

    if isinstance(update_object, Message):
        await update_object.answer(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()  # Отвечаем на callback, чтобы убрать "часики"
        await update_object.message.edit_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


async def _display_orders_paginated(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        current_page: int,
        lang: str,
        is_search: bool = False
):
    """
    Отображает список заказов с пагинацией в админ-панели.

    Функция может отображать либо все заказы, либо результаты поиска,
    в зависимости от флага 'is_search'. Она динамически формирует текст
    сообщения и клавиатуру для навигации по страницам и просмотра деталей заказов.
    Использует локализацию.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение.
    :param state: FSMContext для управления состоянием и данными (например, поисковым запросом).
    :param current_page: Текущий номер отображаемой страницы.
    :param lang: Язык для локализации сообщений.
    :param is_search: Булевый флаг, указывающий, является ли текущее отображение результатами поиска.
                      (True для поиска, False для всех заказов).
    """
    user_id = update_object.from_user.id
    offset = (current_page - 1) * ORDERS_PER_PAGE
    query_text = None

    if is_search:
        data = await state.get_data()
        query_text = data.get("search_query")
        if not query_text:
            logger.error(
                f"Админ {user_id}: Попытка пагинации поиска без search_query в FSM. Возврат в админ-панель.")
            error_message = get_localized_message("error_search_query_not_found", lang)
            await update_object.answer(error_message, show_alert=True)
            await _display_admin_main_menu(update_object, state, lang=lang)
            return

        orders, total_orders = await search_orders(search_query=query_text, offset=offset, limit=ORDERS_PER_PAGE)
    else:
        orders, total_orders = await get_all_orders(offset=offset, limit=ORDERS_PER_PAGE)

    await state.update_data(current_page=current_page)

    total_pages = math.ceil(total_orders / ORDERS_PER_PAGE) if total_orders > 0 else 1

    # --- Формирование текста заголовка ---
    if query_text:
        header_text = get_localized_message(
            "admin_search_results_title", lang
        ).format(query_text=query_text, current_page=current_page, total_pages=total_pages, total_orders=total_orders)
    else:
        header_text = get_localized_message(
            "admin_orders_list_title", lang
        ).format(current_page=current_page, total_pages=total_pages, total_orders=total_orders)

    orders_content_text = header_text + "\n\n"

    if not orders:
        orders_content_text += get_localized_message("no_orders_on_page", lang)

    # --- Кнопки для каждого заказа ---
    order_buttons_builder = InlineKeyboardBuilder()
    for order in orders:
        preview_text = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
        if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
            preview_text += "..."

        button_text = f"ID: {order.id} | {preview_text}"

        # --- ИЗМЕНЕНО ЗДЕСЬ: Добавляем контекст навигации в callback_data ---
        # Формат: view_order_<тип_списка>:<order_id>:<current_page>[:<encoded_query_text>]
        navigation_context = f"all:{current_page}"
        if is_search and query_text:
            encoded_query = urllib.parse.quote_plus(query_text)
            navigation_context = f"search:{current_page}:{encoded_query}"

        order_buttons_builder.add(InlineKeyboardButton(
            text=button_text,
            callback_data=f"view_order_details:{order.id}:{navigation_context}" # Новый callback_data
        ))
    order_buttons_builder.adjust(1)

    # --- Кнопки пагинации ---
    pagination_builder = InlineKeyboardBuilder()
    page_base_prefix = "admin_search_page" if is_search else "admin_all_orders_page"
    encoded_query_text = urllib.parse.quote_plus(query_text) if query_text else ""
    query_param_suffix = f":{encoded_query_text}" if encoded_query_text else ""

    if current_page > 1:
        pagination_builder.button(text="⏮️", callback_data=f"{page_base_prefix}:1{query_param_suffix}")
        if current_page > 5:
            pagination_builder.button(text=get_localized_message("pagination_prev_5", lang),
                                      callback_data=f"{page_base_prefix}:{max(1, current_page - 5)}{query_param_suffix}")
        pagination_builder.button(text=get_localized_message("pagination_prev", lang),
                                  callback_data=f"{page_base_prefix}:{current_page - 1}{query_param_suffix}")

    if current_page < total_pages:
        pagination_builder.button(text=get_localized_message("pagination_next", lang),
                                  callback_data=f"{page_base_prefix}:{current_page + 1}{query_param_suffix}")
        if current_page < total_pages - 4:
            pagination_builder.button(text=get_localized_message("pagination_next_5", lang),
                                      callback_data=f"{page_base_prefix}:{min(total_pages, current_page + 5)}{query_param_suffix}")
        pagination_builder.button(text="⏭️",
                                  callback_data=f"{page_base_prefix}:{total_pages}{query_param_suffix}")

    # Комбинируем клавиатуры: сначала кнопки заказов, затем пагинация, затем кнопка "назад"
    final_keyboard = InlineKeyboardBuilder()
    final_keyboard.attach(order_buttons_builder)

    if total_orders > ORDERS_PER_PAGE:  # Показываем пагинацию только если есть больше одной страницы
        final_keyboard.row(*pagination_builder.buttons)

    # --- Кнопка "Выгрузить в CSV" ---
    export_callback_data = "export_all_orders_csv" if not is_search else f"export_search_orders_csv:{encoded_query_text}"
    final_keyboard.row(InlineKeyboardButton(
        text=get_localized_message("button_export_csv", lang),
        callback_data=export_callback_data
    ))

    final_keyboard.row(InlineKeyboardButton(
        text=get_localized_message("button_back_to_admin_panel", lang),
        callback_data="admin_panel_back"
    ))

    # Отправляем/редактируем сообщение
    if isinstance(update_object, Message):
        await update_object.answer(orders_content_text, reply_markup=final_keyboard.as_markup(),
                                   parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()  # Отвечаем на callback, чтобы убрать "часики"
        await update_object.message.edit_text(orders_content_text, reply_markup=final_keyboard.as_markup(),
                                              parse_mode=ParseMode.HTML)
