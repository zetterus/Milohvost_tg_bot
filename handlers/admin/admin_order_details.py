import logging
import html
import urllib.parse
from typing import Union

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from db import get_order_by_id, update_order_status, update_order_text, delete_order
from config import ORDER_STATUS_KEYS, ORDER_FIELD_NAMES_KEYS, ORDER_FIELD_MAP
from .admin_filters import IsAdmin
from .admin_states import AdminStates
from .admin_utils import _display_orders_paginated, _display_admin_main_menu
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


# --- Вспомогательные функции для отображения деталей заказа ---

async def _display_order_details(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        order_id: int,
        lang: str
):
    """
    Отображает детальную информацию о конкретном заказе с кнопками для управления.
    """
    user_id = update_object.from_user.id
    logger.info(f"Админ {user_id} просматривает детали заказа ID: {order_id}.")

    order = await get_order_by_id(order_id)

    if not order:
        error_message_html = get_localized_message("order_not_found", lang).format(order_id=order_id)
        alert_text = get_localized_message("order_not_found", lang).format(order_id=order_id) # Используем версию без HTML
        if isinstance(update_object, Message):
            await update_object.answer(error_message_html, parse_mode=ParseMode.HTML)
        elif isinstance(update_object, CallbackQuery):
            await update_object.answer(alert_text, show_alert=True)
            await update_object.message.edit_text(error_message_html, parse_mode=ParseMode.HTML)
        # Возвращаемся к списку всех заказов или в главное меню
        await _display_orders_paginated(update_object, state, current_page=1, lang=lang)
        return

    # Сохраняем ID текущего просматриваемого заказа в FSM
    await state.update_data(current_order_id=order_id)

    order_details_text = get_localized_message("order_details_title", lang).format(order_id=order.id) + "\n\n"
    order_details_text += get_localized_message("order_details_user", lang).format(
        username=html.escape(order.username), user_id=order.user_id
    ) + "\n"

    # Локализация статуса
    status_display_name = get_localized_message(f"order_status_{order.status}", lang)
    order_details_text += get_localized_message("order_details_status", lang).format(
        status=status_display_name
    ) + "\n"

    # Добавляем все поля заказа
    for field_key in ORDER_FIELD_NAMES_KEYS.keys():
        field_name_localized = get_localized_message(ORDER_FIELD_NAMES_KEYS[field_key], lang)
        field_value = getattr(order, field_key)

        value_to_display = field_value
        if field_key == "payment_method" and field_value:
            payment_options = ORDER_FIELD_MAP.get("payment_method", {}).get("options_keys", {})
            localized_payment_method_key = next((k for k, v in payment_options.items() if v == field_value), None)
            if localized_payment_method_key:
                value_to_display = get_localized_message(localized_payment_method_key, lang)
        elif field_key == "delivery_notes" and (field_value is None or field_value.strip() == '-' or field_value.strip().lower() == get_localized_message("no_notes_keyword", lang).lower()):
            value_to_display = get_localized_message("no_notes_display", lang)
        elif field_value is None:
            value_to_display = get_localized_message("not_specified", lang)

        escaped_value = html.escape(str(value_to_display)) if value_to_display is not None else ""

        if field_key == "order_text":
            order_details_text += get_localized_message("order_details_order_text", lang).format(
                order_text=escaped_value
            ) + "\n"
        else:
            order_details_text += f"<b>{field_name_localized}</b>: {escaped_value}\n"

    order_details_text += get_localized_message("order_details_created_at", lang).format(
        created_at=order.created_at.strftime('%d.%m.%Y %H:%M')
    ) + "\n"

    keyboard = InlineKeyboardBuilder()

    # Кнопки для изменения статуса
    for status_key in ORDER_STATUS_KEYS:
        if status_key != order.status: # Не показываем кнопку для текущего статуса
            status_name = get_localized_message(f"order_status_{status_key}", lang)
            keyboard.button(
                text=get_localized_message("admin_change_status_button", lang).format(status_name=status_name),
                callback_data=f"admin_change_order_status:{order.id}:{status_key}"
            )
    keyboard.adjust(2) # Размещаем кнопки статусов по 2 в ряд

    # Кнопки редактирования и удаления
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_edit_text_button", lang),
                                      callback_data=f"admin_edit_order_text:{order.id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_delete_order_button", lang),
                                      callback_data=f"admin_confirm_delete_order:{order.id}"))

    # --- ИЗМЕНЕНО ЗДЕСЬ: Динамическая кнопка "Назад" ---
    data = await state.get_data()
    origin_type = data.get("origin_type")
    origin_page = data.get("origin_page", 1) # По умолчанию страница 1
    origin_search_query = data.get("origin_search_query")

    back_callback_data = "admin_panel_back" # Дефолтное значение, если нет информации об источнике

    if origin_type == "all":
        back_callback_data = f"admin_all_orders_page:{origin_page}"
    elif origin_type == "search" and origin_search_query:
        encoded_query = urllib.parse.quote_plus(origin_search_query)
        back_callback_data = f"admin_search_page:{origin_page}:{encoded_query}"

    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_orders", lang),
                                      callback_data=back_callback_data))

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(order_details_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(order_details_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# --- Хэндлеры для просмотра деталей заказа ---

@router.callback_query(F.data.startswith("view_order_details:"), IsAdmin())
async def view_order_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает нажатие на кнопку заказа в списке, чтобы показать его детали.
    Теперь также сохраняет контекст навигации (откуда пришли).
    """
    user_id = callback.from_user.id
    try:
        parts = callback.data.split(":")
        order_id = int(parts[1])
        origin_type = parts[2] # 'all' или 'search'
        origin_page = int(parts[3])
        origin_search_query = urllib.parse.unquote_plus(parts[4]) if len(parts) > 4 else None # Для поиска

        # --- ДОБАВЛЕНО: Сохраняем контекст навигации в FSM ---
        await state.update_data(
            origin_type=origin_type,
            origin_page=origin_page,
            origin_search_query=origin_search_query
        )

    except (ValueError, IndexError) as e:
        logger.error(f"Админ {user_id}: Неверный формат callback_data для просмотра заказа: {callback.data}. Ошибка: {e}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} запросил просмотр заказа ID: {order_id} из {origin_type} (страница {origin_page}).")
    await _display_order_details(callback, state, order_id, lang)


# --- Хэндлеры для изменения статуса заказа ---

@router.callback_query(F.data.startswith("admin_change_order_status:"), IsAdmin())
async def admin_change_order_status_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает изменение статуса заказа.
    """
    user_id = callback.from_user.id
    try:
        parts = callback.data.split(":")
        order_id = int(parts[1])
        new_status = parts[2]
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для изменения статуса: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} меняет статус заказа ID: {order_id} на {new_status}.")

    success = await update_order_status(order_id, new_status)
    status_name = get_localized_message(f"order_status_{new_status}", lang)

    if success:
        alert_text = get_localized_message("admin_status_changed_alert", lang).format(
            order_id=order_id, status_name=status_name
        )
        await callback.answer(alert_text, show_alert=True)
    else:
        alert_text = get_localized_message("admin_status_change_failed_alert", lang).format(
            order_id=order_id
        )
        await callback.answer(alert_text, show_alert=True)

    # После изменения статуса обновляем детали заказа
    await _display_order_details(callback, state, order_id, lang)


# --- Хэндлеры для редактирования текста заказа ---

@router.callback_query(F.data.startswith("admin_edit_order_text:"), IsAdmin())
async def admin_edit_order_text_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает запрос на редактирование текста заказа.
    """
    user_id = callback.from_user.id
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для редактирования текста: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} запросил редактирование текста заказа ID: {order_id}.")

    # Сохраняем ID заказа в FSM для последующей обработки нового текста
    await state.update_data(editing_order_id=order_id)
    await state.set_state(AdminStates.waiting_for_new_order_text)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_edit_order_text_cancel_button", lang),
                                      callback_data=f"admin_cancel_edit_order_text:{order_id}"))
    reply_markup = keyboard.as_markup()

    await callback.message.edit_text(
        get_localized_message("admin_edit_order_text_prompt", lang).format(order_id=order_id),
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_new_order_text, IsAdmin())
async def admin_process_new_order_text(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает новый текст заказа, введенный админом.
    """
    user_id = message.from_user.id
    new_text = message.text.strip()
    data = await state.get_data()
    order_id = data.get("editing_order_id")

    if not order_id:
        logger.error(f"Админ {user_id}: Не найден ID заказа для редактирования текста в FSM.")
        await message.answer(get_localized_message("admin_edit_text_error_data_not_found", lang), parse_mode=ParseMode.HTML)
        await state.clear()
        await _display_admin_main_menu(message, state, lang=lang) # Возвращаемся в главное меню
        return

    logger.info(f"Админ {user_id} ввел новый текст '{new_text}' для заказа ID: {order_id}.")

    success = await update_order_text(order_id, new_text)

    if success:
        await message.answer(get_localized_message("admin_order_text_updated_success", lang).format(order_id=order_id), parse_mode=ParseMode.HTML)
    else:
        await message.answer(get_localized_message("admin_order_text_update_failed", lang).format(order_id=order_id), parse_mode=ParseMode.HTML)

    await state.clear()
    # Возвращаемся к деталям заказа после обновления
    await _display_order_details(message, state, order_id, lang)


@router.callback_query(F.data.startswith("admin_cancel_edit_order_text:"), IsAdmin())
async def admin_cancel_edit_order_text_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает отмену редактирования текста заказа.
    """
    user_id = callback.from_user.id
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для отмены редактирования: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} отменил редактирование текста заказа ID: {order_id}.")
    await state.clear()
    alert_text = get_localized_message("admin_edit_text_cancelled_alert", lang)
    await callback.answer(alert_text, show_alert=True)
    await _display_order_details(callback, state, order_id, lang)


# --- Хэндлеры для удаления заказа ---

@router.callback_query(F.data.startswith("admin_confirm_delete_order:"), IsAdmin())
async def admin_confirm_delete_order_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Запрашивает подтверждение удаления заказа.
    """
    user_id = callback.from_user.id
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для подтверждения удаления: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} запросил подтверждение удаления заказа ID: {order_id}.")

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_yes_delete", lang),
                                      callback_data=f"admin_delete_order:{order_id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_no_cancel", lang),
                                      callback_data=f"view_order_details:{order_id}:all:1")) # Возвращаемся к деталям заказа, если отмена
    keyboard.adjust(1)

    await callback.message.edit_text(
        get_localized_message("admin_confirm_delete_prompt", lang).format(order_id=order_id),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_order:"), IsAdmin())
async def admin_delete_order_confirmed_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Удаляет заказ после подтверждения.
    """
    user_id = callback.from_user.id
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для удаления заказа: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} подтвердил удаление заказа ID: {order_id}.")

    success = await delete_order(order_id)

    if success:
        alert_text = get_localized_message("admin_order_deleted_success_alert", lang).format(order_id=order_id)
        await callback.answer(alert_text, show_alert=True)
        await callback.message.edit_text(
            get_localized_message("admin_order_deleted_success_message", lang).format(order_id=order_id),
            parse_mode=ParseMode.HTML
        )
    else:
        alert_text = get_localized_message("admin_order_delete_failed_alert", lang).format(order_id=order_id)
        await callback.answer(alert_text, show_alert=True)
        await callback.message.edit_text(
            get_localized_message("admin_order_delete_failed_alert", lang).format(order_id=order_id),
            parse_mode=ParseMode.HTML
        )

    await state.clear()
    # Возвращаемся к списку всех заказов после удаления
    await _display_orders_paginated(callback, state, current_page=1, lang=lang)
