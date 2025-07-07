import logging
import urllib.parse
import html

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from config import ORDER_STATUS_KEYS, ORDER_FIELD_NAMES_KEYS, ORDER_FIELDS_CONFIG, \
    ORDER_FIELD_MAP  # <-- Добавлены ORDER_FIELDS_CONFIG, ORDER_FIELD_MAP
from db import get_order_by_id, update_order_status, update_order_text, delete_order
from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from .admin_states import AdminStates
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


# --- Вспомогательная функция для формирования деталей заказа и клавиатуры ---
async def _build_order_details_and_keyboard(
        order_id: int,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
) -> tuple[str, InlineKeyboardMarkup | None]:
    """
    Формирует текст с деталями заказа и соответствующую инлайн-клавиатуру.
    Используется для предотвращения дублирования кода.
    Использует локализацию для всех отображаемых текстов.
    """
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    order = await get_order_by_id(order_id)
    if not order:
        return get_localized_message("order_not_found", lang), None

    # Получаем локализованное отображение статуса
    display_status = get_localized_message(f"order_status_{order.status}", lang)

    order_details_parts = []

    # Заголовок
    order_details_parts.append(get_localized_message("order_details_title", lang).format(order_id=order.id))
    order_details_parts.append("")  # Пустая строка для отступа

    # Общая информация о пользователе и статусе
    order_details_parts.append(
        get_localized_message("order_details_user", lang).format(username=order.username or 'N/A',
                                                                 user_id=order.user_id))
    order_details_parts.append(get_localized_message("order_details_status", lang).format(status=display_status))

    # Динамическое добавление полей заказа
    for field_config in ORDER_FIELDS_CONFIG:
        key = field_config["key"]

        # Получаем локализованное название поля из ORDER_FIELD_NAMES_KEYS
        display_name_key = ORDER_FIELD_NAMES_KEYS.get(key, key)  # Fallback на сам ключ
        display_name = get_localized_message(display_name_key, lang)

        value = getattr(order, key, None)  # Получаем значение из объекта Order

        # Специальная обработка для payment_method и delivery_notes
        value_to_display = value
        if key == "payment_method" and value:
            payment_field_config = ORDER_FIELD_MAP.get("payment_method")
            if payment_field_config and "options_keys" in payment_field_config:
                for button_key, val in payment_field_config["options_keys"].items():
                    if val == value:
                        value_to_display = get_localized_message(button_key, lang)
                        break
        elif key == "delivery_notes" and (
                value is None or str(value).strip() == '-' or str(value).strip().lower() == get_localized_message(
                "no_notes_keyword", lang).lower()):
            value_to_display = get_localized_message("no_notes_display", lang)

        # Экранируем значение перед добавлением в текст
        escaped_value = html.escape(str(value_to_display)) if value_to_display is not None else get_localized_message(
            "not_specified", lang)

        # Для order_text используем <code> тег
        if key == "order_text":
            order_details_parts.append(f"<b>{display_name.capitalize()}</b>:\n<code>{escaped_value}</code>")
        else:
            order_details_parts.append(f"<b>{display_name.capitalize()}</b>: {escaped_value}")

    # Дата создания
    order_details_parts.append(get_localized_message("order_details_created_at", lang).format(
        created_at=order.created_at.strftime('%d.%m.%Y %H:%M:%S')))

    order_details_text = "\n".join(order_details_parts)

    status_keyboard = InlineKeyboardBuilder()

    # Кнопки смены статуса
    for status_key in ORDER_STATUS_KEYS:
        if status_key != order.status:
            localized_status_name = get_localized_message(f"order_status_{status_key}", lang)
            status_keyboard.add(InlineKeyboardButton(
                text=get_localized_message("admin_change_status_button", lang).format(
                    status_name=localized_status_name),
                callback_data=f"admin_change_status_{order.id}_{status_key}"
            ))
    status_keyboard.adjust(2)

    # Кнопки редактирования и удаления
    status_keyboard.row(
        InlineKeyboardButton(
            text=get_localized_message("admin_edit_text_button", lang),
            callback_data=f"admin_edit_order_text_{order.id}"
        ),
        InlineKeyboardButton(
            text=get_localized_message("admin_delete_order_button", lang),
            callback_data=f"admin_confirm_delete_order_{order.id}"
        )
    )

    # Логика кнопки "Назад к заказам/поиску"
    data = await state.get_data()
    current_page = data.get("current_page", 1)
    search_query = data.get("search_query")

    if search_query:
        encoded_query = urllib.parse.quote_plus(search_query)
        status_keyboard.row(InlineKeyboardButton(
            text=get_localized_message("button_back_to_search", lang),
            callback_data=f"admin_search_page:{current_page}:{encoded_query}"
        ))
    else:
        status_keyboard.row(InlineKeyboardButton(
            text=get_localized_message("button_back_to_orders", lang),
            callback_data=f"admin_all_orders_page:{current_page}"
        ))

    return order_details_text, status_keyboard.as_markup()


@router.callback_query(F.data.startswith("view_order_"), IsAdmin())
async def admin_view_order_details_callback(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обрабатывает нажатие кнопки "Заказ #ID" для детального просмотра заказа.
    Показывает подробную информацию о заказе и кнопки для изменения статуса.
    """
    user_id = callback.from_user.id
    order_id = int(callback.data.split("_")[2])
    logger.info(f"Админ {user_id} просматривает детали заказа ID {order_id}.")

    order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state, storage=storage,
                                                                                  storage_key=storage_key)

    await callback.message.edit_text(
        order_details_text,
        reply_markup=keyboard_markup,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_change_status_"), IsAdmin())
async def admin_change_order_status_callback(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обрабатывает изменение статуса заказа.
    """
    user_id = callback.from_user.id
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    try:
        _, _, _, order_id_str, new_status = callback.data.split('_', 4)
        order_id = int(order_id_str)
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для изменения статуса: {callback.data}")
        await bot.answer_callback_query(callback.id, get_localized_message("error_invalid_callback_data", lang),
                                        show_alert=True)
        return

    logger.info(f"Админ {user_id} меняет статус заказа ID {order_id} на '{new_status}'.")

    updated_order = await update_order_status(order_id, new_status)

    if updated_order:
        display_status = get_localized_message(f"order_status_{updated_order.status}", lang)
        await bot.answer_callback_query(callback.id,
                                        text=get_localized_message("admin_status_changed_alert", lang).format(
                                            order_id=order_id, status_name=display_status), show_alert=True)

        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state, storage=storage,
                                                                                      storage_key=storage_key)

        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await bot.answer_callback_query(callback.id, get_localized_message("admin_status_change_failed_alert", lang),
                                        show_alert=True)
        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state, storage=storage,
                                                                                      storage_key=storage_key)
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )


@router.callback_query(F.data.startswith("admin_edit_order_text_"), IsAdmin())
async def admin_edit_order_text_callback(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обрабатывает нажатие кнопки "Редактировать текст заказа".
    Запрашивает новый текст и переводит в состояние ожидания ввода.
    """
    user_id = callback.from_user.id
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    try:
        order_id = int(callback.data.split("_", 4)[4])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для редактирования текста: {callback.data}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Админ {user_id} инициировал редактирование текста заказа ID {order_id}.")

    await state.update_data(
        editing_order_id=order_id,
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )
    await state.set_state(AdminStates.waiting_for_order_text_edit)

    await callback.message.edit_text(
        get_localized_message("admin_edit_order_text_prompt", lang).format(order_id=order_id),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_localized_message("admin_edit_order_text_cancel_button", lang),
                                  callback_data=f"view_order_{order_id}")]
        ]),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_for_order_text_edit), IsAdmin())
async def admin_process_new_order_text(
        message: Message,
        state: FSMContext,
        bot: Bot,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обрабатывает ввод нового текста для заказа.
    Обновляет заказ в базе данных и возвращается к деталям заказа,
    редактируя предыдущее сообщение.
    """
    user_id = message.from_user.id
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    data = await state.get_data()
    order_id = data.get("editing_order_id")
    original_message_id = data.get("original_message_id")
    original_chat_id = data.get("original_chat_id")

    if not all([order_id, original_message_id, original_chat_id]):
        logger.error(f"Админ {user_id}: Не найдены все данные для редактирования текста в FSM.")
        await message.answer(
            get_localized_message("admin_edit_text_error_data_not_found", lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang),
                                      callback_data="admin_panel_back")]
            ]),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return

    new_order_text = message.text.strip()
    logger.info(f"Админ {user_id} ввел новый текст для заказа ID {order_id}.")

    updated_order = await update_order_text(order_id=order_id, new_text=new_order_text)

    await state.clear()

    if updated_order:
        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state, storage=storage,
                                                                                      storage_key=storage_key)
        await bot.edit_message_text(
            chat_id=original_chat_id,
            message_id=original_message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )
        await message.answer(get_localized_message("admin_order_text_updated_success", lang).format(order_id=order_id),
                             parse_mode=ParseMode.HTML)
    else:
        await message.answer(get_localized_message("admin_order_text_update_failed", lang), parse_mode=ParseMode.HTML)
        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state, storage=storage,
                                                                                      storage_key=storage_key)
        await bot.edit_message_text(
            chat_id=original_chat_id,
            message_id=original_message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )


@router.callback_query(F.data.startswith("admin_confirm_delete_order_"), IsAdmin())
async def admin_confirm_delete_order_callback(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Запрашивает подтверждение удаления заказа.
    """
    user_id = callback.from_user.id
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    try:
        order_id = int(callback.data.split("_", 4)[4])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для подтверждения удаления: {callback.data}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Админ {user_id} запрашивает подтверждение удаления заказа ID {order_id}.")

    await state.update_data(
        deleting_order_id=order_id,
        original_message_id_for_delete_confirm=callback.message.message_id,
        original_chat_id_for_delete_confirm=callback.message.chat.id,
    )

    confirm_keyboard = InlineKeyboardBuilder()
    confirm_keyboard.row(
        InlineKeyboardButton(text=get_localized_message("button_yes_delete", lang),
                             callback_data=f"admin_delete_order_{order_id}"),
        InlineKeyboardButton(text=get_localized_message("button_no_cancel", lang),
                             callback_data=f"view_order_{order_id}")
    )

    await callback.message.edit_text(
        get_localized_message("admin_confirm_delete_prompt", lang).format(order_id=order_id),
        reply_markup=confirm_keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_order_"), IsAdmin())
async def admin_delete_order_callback(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Выполняет удаление заказа после подтверждения.
    """
    user_id = callback.from_user.id
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    try:
        order_id = int(callback.data.split("_", 3)[3])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для удаления: {callback.data}")
        await bot.answer_callback_query(callback.id, get_localized_message("error_invalid_callback_data", lang),
                                        show_alert=True)
        return

    logger.info(f"Админ {user_id} подтвердил удаление заказа ID {order_id}.")

    deleted = await delete_order(order_id=order_id)
    await state.clear()

    if deleted:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=get_localized_message("admin_order_deleted_success_message", lang).format(order_id=order_id),
            parse_mode=ParseMode.HTML
        )
        await bot.answer_callback_query(callback.id,
                                        text=get_localized_message("admin_order_deleted_success_alert", lang).format(
                                            order_id=order_id))

        await _display_orders_paginated(callback, state, storage=storage, storage_key=storage_key, current_page=1,
                                        is_search=False)
    else:
        await bot.answer_callback_query(callback.id, get_localized_message("admin_order_delete_failed_alert", lang),
                                        show_alert=True)
        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state, storage=storage,
                                                                                      storage_key=storage_key)
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )
