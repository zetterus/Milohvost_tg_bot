import logging
import html
from typing import Union

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter

from db import (
    get_active_help_message_from_db,
    add_help_message,
    get_help_message_by_id,
    set_active_help_message,
    deactivate_help_message,  # Добавлен импорт для деактивации
    delete_help_message,
    get_all_help_messages,
    update_help_message_language  # НОВЫЙ ИМПОРТ
)
from .admin_filters import IsAdmin
from .admin_states import AdminStates
from localization import get_localized_message, get_available_languages  # НОВЫЙ ИМПОРТ: get_available_languages

logger = logging.getLogger(__name__)
router = Router()


# --- Вспомогательные функции для управления сообщениями помощи ---

async def _display_help_messages_menu(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        lang: str
):
    """
    Отображает главное меню управления сообщениями помощи.
    Показывает текущее активное сообщение (если есть) и кнопки действий.
    """
    user_id = update_object.from_user.id
    logger.info(f"Админ {user_id} вошел в управление сообщениями помощи.")

    # Получаем статус активных сообщений для всех языков
    available_langs = get_available_languages()
    active_status_parts = []
    for l_code in available_langs:
        active_message = await get_active_help_message_from_db(l_code)
        if active_message:
            status_text = get_localized_message("admin_help_active_message_status_lang", lang).format(
                lang_code=l_code.upper(), message_id=active_message.id
            )
        else:
            status_text = get_localized_message("admin_help_no_active_message_lang", lang).format(
                lang_code=l_code.upper()
            )
        active_status_parts.append(status_text)

    current_active_status = "\n".join(active_status_parts)

    title_text = get_localized_message("admin_help_manage_title", lang).format(
        current_active_status=current_active_status
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("admin_button_create_help_message", lang),
                    callback_data="admin_create_help_message")
    keyboard.button(text=get_localized_message("admin_button_manage_existing_help_messages", lang),
                    callback_data="admin_view_all_help_messages")
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang),
                                      callback_data="admin_panel_back"))
    keyboard.adjust(1)

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(title_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.message.edit_text(title_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        await update_object.answer()


async def _display_help_message_details(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        message_id: int,
        lang: str
):
    """
    Отображает детальную информацию о конкретном сообщении помощи с кнопками для управления.
    """
    user_id = update_object.from_user.id
    logger.info(f"Админ {user_id} просматривает детали сообщения помощи ID: {message_id}.")

    message_obj = await get_help_message_by_id(message_id)

    if not message_obj:
        error_text = get_localized_message("admin_help_message_not_found", lang).format(message_id=message_id)
        if isinstance(update_object, CallbackQuery):
            await update_object.answer(error_text, show_alert=True)
            await update_object.message.edit_text(error_text, parse_mode=ParseMode.HTML)
        elif isinstance(update_object, Message):
            await update_object.answer(error_text, parse_mode=ParseMode.HTML)
        await _display_help_messages_menu(update_object, state, lang)
        return

    # Формируем текст с деталями сообщения
    status_emoji = "✅" if message_obj.is_active else "❌"
    status_text = get_localized_message("admin_help_status_active",
                                        lang) if message_obj.is_active else get_localized_message(
        "admin_help_status_inactive", lang)

    details_text = get_localized_message("admin_help_message_details_title", lang) + "\n\n"
    details_text += f"<b>{get_localized_message('admin_help_message_id_label', lang)}</b>: <code>{message_obj.id}</code>\n"
    details_text += f"<b>{get_localized_message('admin_help_message_language_label', lang)}</b>: {message_obj.language_code.upper()}\n"  # НОВОЕ ПОЛЕ
    details_text += f"<b>{get_localized_message('admin_help_message_status_label', lang)}</b>: {status_emoji} {status_text} {status_emoji}\n"
    details_text += f"<b>{get_localized_message('field_name_order_text', lang)}</b>:\n<code>{html.escape(message_obj.message_text)}</code>\n\n"
    details_text += f"<b>{get_localized_message('admin_help_message_created_at_label', lang)}</b>: {message_obj.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    details_text += f"<b>{get_localized_message('admin_help_message_updated_at_label', lang)}</b>: {message_obj.updated_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    details_text += get_localized_message("admin_help_what_to_do", lang)

    keyboard = InlineKeyboardBuilder()

    # --- Кнопки выбора языка ---
    language_buttons = []
    available_languages = get_available_languages()
    for lang_code in available_languages:
        button_text_key = f"admin_button_lang_{lang_code}"
        button_text = get_localized_message(button_text_key, lang)
        # Добавляем эмодзи или индикатор для текущего языка сообщения
        if lang_code == message_obj.language_code:
            button_text = f"✅ {button_text}"
        language_buttons.append(InlineKeyboardButton(
            text=button_text,
            callback_data=f"admin_set_help_msg_lang:{message_obj.id}:{lang_code}"
        ))
    keyboard.row(*language_buttons)  # Добавляем кнопки выбора языка в один ряд

    # --- Кнопки действий (Деактивировать/Активировать, Удалить) ---
    if message_obj.is_active:
        keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_deactivate_help_message", lang),
                                          callback_data=f"admin_deactivate_help_message:{message_id}"))
    else:
        keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_activate_help_message", lang),
                                          callback_data=f"admin_activate_help_message:{message_id}"))

    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_delete", lang),
                                      callback_data=f"admin_confirm_delete_help_message:{message_id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_messages_list", lang),
                                      callback_data="admin_view_all_help_messages"))
    keyboard.adjust(1)  # Выравниваем основные кнопки в столбец

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(details_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.message.edit_text(details_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        await update_object.answer()


# --- Хэндлеры для управления сообщениями помощи ---

@router.callback_query(F.data == "admin_manage_help_messages", IsAdmin())
async def admin_manage_help_messages_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: отображает главное меню управления сообщениями помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} нажал 'Управление помощью'.")
    await _display_help_messages_menu(callback, state, lang)


@router.callback_query(F.data == "admin_create_help_message", IsAdmin())
async def admin_create_help_message(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: начинает процесс создания нового сообщения помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} начал создание нового сообщения помощи.")
    await state.set_state(AdminStates.waiting_for_help_message_text)
    await callback.message.edit_text(get_localized_message("admin_help_prompt_new_message_text", lang),
                                     parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(AdminStates.waiting_for_help_message_text, IsAdmin())
async def admin_process_new_help_message_text(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обработчик сообщения: получает текст нового сообщения помощи и предлагает его сохранение.
    """
    user_id = message.from_user.id
    message_text = message.text.strip()
    if not message_text:
        await message.answer(get_localized_message("admin_help_empty_message_error", lang))
        return

    await state.update_data(new_help_message_text=message_text)
    logger.info(f"Админ {user_id} ввел текст для нового сообщения помощи.")

    keyboard = InlineKeyboardBuilder()
    # Кнопки для сохранения и активации, только сохранения, или отмены
    keyboard.button(text=get_localized_message("admin_button_save_and_activate", lang),
                    callback_data="admin_save_help_message:activate")
    keyboard.button(text=get_localized_message("admin_button_save_only", lang),
                    callback_data="admin_save_help_message:no_activate")
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_cancel_creation", lang),
                                      callback_data="admin_cancel_help_message_creation"))
    keyboard.adjust(1)

    preview_text = get_localized_message("admin_help_preview_title", lang) + "\n\n" + \
                   html.escape(message_text[:200]) + ("..." if len(message_text) > 200 else "") + "\n\n" + \
                   get_localized_message("admin_help_what_to_do", lang)

    await message.answer(preview_text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("admin_save_help_message:"), IsAdmin())
async def admin_save_help_message(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: сохраняет новое сообщение помощи в БД.
    """
    user_id = callback.from_user.id
    data = await state.get_data()
    message_text = data.get("new_help_message_text")
    action = callback.data.split(":")[1]  # 'activate' или 'no_activate'

    if not message_text:
        logger.error(f"Админ {user_id}: Попытка сохранить сообщение помощи без текста.")
        await callback.answer(get_localized_message("admin_help_error_text_not_found", lang), show_alert=True)
        await state.clear()
        await _display_help_messages_menu(callback, state, lang)
        return

    is_active = (action == "activate")

    # НОВОЕ: Запрашиваем язык для активации, если выбрано "активировать"
    if is_active:
        await state.update_data(temp_message_text=message_text)  # Сохраняем текст временно
        await state.set_state(
            AdminStates.waiting_for_help_message_selection)  # Временно используем это состояние для выбора языка

        keyboard = InlineKeyboardBuilder()
        available_languages = get_available_languages()
        for lang_code in available_languages:
            button_text_key = f"admin_button_lang_{lang_code}"
            button_text = get_localized_message(button_text_key, lang)
            keyboard.button(text=button_text, callback_data=f"admin_add_help_msg_with_lang:{lang_code}")
        keyboard.adjust(2)
        keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_cancel_creation", lang),
                                          callback_data="admin_cancel_help_message_creation"))

        await callback.message.edit_text(
            get_localized_message("admin_help_prompt_activate_language", lang),
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        return

    # Если не 'activate', сразу сохраняем с текущим языком админа
    new_message = await add_help_message(message_text, lang, is_active=False)  # По умолчанию неактивно

    if new_message:
        alert_text = get_localized_message("admin_help_saved_only", lang).format(message_id=new_message.id)
        await callback.answer(alert_text, show_alert=True)
        await callback.message.edit_text(alert_text, parse_mode=ParseMode.HTML)
    else:
        alert_text = get_localized_message("error_order_processing", lang)  # Используем общую ошибку
        await callback.answer(alert_text, show_alert=True)
        await callback.message.edit_text(alert_text, parse_mode=ParseMode.HTML)

    await state.clear()
    await _display_help_messages_menu(callback, state, lang)


@router.callback_query(F.data.startswith("admin_add_help_msg_with_lang:"), IsAdmin(),
                       StateFilter(AdminStates.waiting_for_help_message_selection))
async def admin_add_help_message_with_lang(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: сохраняет новое сообщение помощи с выбранным языком и активирует его.
    """
    user_id = callback.from_user.id
    data = await state.get_data()
    message_text = data.get("temp_message_text")  # Получаем текст из временного хранилища
    selected_lang_code = callback.data.split(":")[1]

    if not message_text:
        logger.error(f"Админ {user_id}: Попытка сохранить сообщение помощи без текста после выбора языка.")
        await callback.answer(get_localized_message("admin_help_error_text_not_found", lang), show_alert=True)
        await state.clear()
        await _display_help_messages_menu(callback, state, lang)
        return

    new_message = await add_help_message(message_text, selected_lang_code, is_active=True)

    if new_message:
        alert_text = get_localized_message("admin_help_saved_and_activated", lang).format(message_id=new_message.id)
        await callback.answer(alert_text, show_alert=True)
        await callback.message.edit_text(alert_text, parse_mode=ParseMode.HTML)
    else:
        alert_text = get_localized_message("error_order_processing", lang)
        await callback.answer(alert_text, show_alert=True)
        await callback.message.edit_text(alert_text, parse_mode=ParseMode.HTML)

    await state.clear()
    await _display_help_messages_menu(callback, state, lang)


@router.callback_query(F.data == "admin_cancel_help_message_creation", IsAdmin())
async def admin_cancel_help_message_creation(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: отменяет создание нового сообщения помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} отменил создание сообщения помощи.")
    await state.clear()
    alert_text = get_localized_message("admin_help_creation_cancelled", lang)
    await callback.answer(alert_text, show_alert=True)
    await _display_help_messages_menu(callback, state, lang)


@router.callback_query(F.data == "admin_view_all_help_messages", IsAdmin())
async def admin_view_all_help_messages(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: отображает список всех сообщений помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} просматривает все сообщения помощи.")

    all_messages = await get_all_help_messages()

    messages_text = get_localized_message("admin_help_all_messages_title", lang) + "\n\n"

    if not all_messages:
        messages_text += get_localized_message("admin_help_no_saved_messages", lang)
    else:
        for msg in all_messages:
            status_emoji = "✅" if msg.is_active else "❌"
            preview_text = html.escape(msg.message_text[:50])
            if len(msg.message_text) > 50:
                preview_text += "..."
            messages_text += get_localized_message("admin_help_message_entry", lang).format(
                status_emoji=status_emoji,
                message_id=msg.id,
                preview_text=preview_text,
                created_at=msg.created_at.strftime('%d.%m.%Y %H:%M')
            ) + "\n"

    keyboard = InlineKeyboardBuilder()
    if all_messages:
        for msg in all_messages:
            keyboard.row(InlineKeyboardButton(
                text=get_localized_message("admin_help_button_select", lang).format(message_id=msg.id),
                callback_data=f"admin_show_help_message_details:{msg.id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_help_management", lang),
                                      callback_data="admin_manage_help_messages"))
    keyboard.adjust(1)

    await callback.message.edit_text(messages_text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_show_help_message_details:"), IsAdmin())
async def admin_show_help_message_details(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: отображает детали выбранного сообщения помощи.
    """
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для деталей сообщения помощи: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    await _display_help_message_details(callback, state, message_id, lang)


@router.callback_query(F.data.startswith("admin_activate_help_message:"), IsAdmin())
async def admin_activate_help_message_callback(
        callback: CallbackQuery,
        state: FSMContext, # Добавлен аргумент state
        lang: str
):
    """
    Обработчик callback-запроса: активирует сообщение помощи.
    """
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для активации сообщения помощи: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} активирует сообщение помощи ID: {message_id}.")

    # Получаем текущее сообщение, чтобы узнать его язык
    message_obj = await get_help_message_by_id(message_id)
    if not message_obj:
        alert_text = get_localized_message("admin_help_activate_failed", lang).format(message_id=message_id)
        await callback.answer(alert_text, show_alert=True)
        return

    success = await set_active_help_message(message_id, message_obj.language_code)  # Передаем язык

    if success:
        alert_text = get_localized_message("admin_help_activated_success", lang).format(message_id=message_id)
        await callback.answer(alert_text, show_alert=True)
        # Обновляем сообщение с деталями после активации
        await _display_help_message_details(callback, state, message_id, lang)
    else:
        alert_text = get_localized_message("admin_help_activate_failed", lang).format(message_id=message_id)
        await callback.answer(alert_text, show_alert=True)


@router.callback_query(F.data.startswith("admin_deactivate_help_message:"), IsAdmin())
async def admin_deactivate_help_message_callback(
        callback: CallbackQuery,
        state: FSMContext, # Добавлен аргумент state
        lang: str
):
    """
    Обработчик callback-запроса: деактивирует сообщение помощи.
    """
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для деактивации сообщения помощи: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} деактивирует сообщение помощи ID: {message_id}.")

    success = await deactivate_help_message(message_id)

    if success:
        alert_text = get_localized_message("admin_help_deactivated_success", lang).format(message_id=message_id)
        await callback.answer(alert_text, show_alert=True)
        # Обновляем сообщение с деталями после деактивации
        await _display_help_message_details(callback, state, message_id, lang)
    else:
        alert_text = get_localized_message("admin_help_deactivate_failed", lang).format(message_id=message_id)
        await callback.answer(alert_text, show_alert=True)


@router.callback_query(F.data.startswith("admin_confirm_delete_help_message:"), IsAdmin())
async def admin_confirm_delete_help_message(
        callback: CallbackQuery,
        lang: str
):
    """
    Обработчик callback-запроса: запрашивает подтверждение удаления сообщения помощи.
    """
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для подтверждения удаления сообщения помощи: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} запрашивает подтверждение удаления сообщения помощи ID: {message_id}.")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_yes_delete", lang),
                    callback_data=f"admin_delete_help_message:{message_id}")
    keyboard.button(text=get_localized_message("button_no_cancel", lang),
                    callback_data=f"admin_show_help_message_details:{message_id}")  # Возврат к деталям сообщения
    keyboard.adjust(2)

    await callback.message.edit_text(
        get_localized_message("admin_confirm_delete_help_message_prompt", lang).format(message_id=message_id),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_help_message:"), IsAdmin())
async def admin_delete_help_message_confirmed(
        callback: CallbackQuery,
        state: FSMContext, # Добавлен аргумент state
        lang: str
):
    """
    Обработчик callback-запроса: удаляет сообщение помощи из БД после подтверждения.
    """
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для удаления сообщения помощи: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} подтвердил удаление сообщения помощи ID: {message_id}.")

    success = await delete_help_message(message_id)

    if success:
        alert_text = get_localized_message("admin_help_deleted_success", lang).format(message_id=message_id)
        await callback.message.edit_text(
            alert_text,
            parse_mode=ParseMode.HTML
        )
        await callback.answer(alert_text, show_alert=True)
    else:
        alert_text = get_localized_message("admin_help_delete_failed", lang).format(message_id=message_id)
        await callback.answer(alert_text, show_alert=True)
        await callback.message.edit_text(
            alert_text,
            parse_mode=ParseMode.HTML
        )
    # Возвращаемся к списку сообщений помощи после удаления
    await _display_help_messages_menu(callback, state, lang)


@router.callback_query(F.data.startswith("admin_set_help_msg_lang:"), IsAdmin())
async def admin_set_help_message_language(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса: устанавливает язык для сообщения помощи.
    """
    user_id = callback.from_user.id
    try:
        parts = callback.data.split(":")
        message_id = int(parts[1])
        new_lang_code = parts[2]
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для установки языка сообщения помощи: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} меняет язык сообщения помощи ID {message_id} на '{new_lang_code}'.")

    updated_message = await update_help_message_language(message_id, new_lang_code)

    if updated_message:
        alert_text = get_localized_message("admin_help_language_changed_success", lang).format(
            message_id=message_id, new_lang=new_lang_code.upper()
        )
        await callback.answer(alert_text, show_alert=True)
        # Обновляем отображение деталей сообщения
        await _display_help_message_details(callback, state, message_id, lang)
    else:
        alert_text = get_localized_message("admin_help_language_change_failed", lang).format(message_id=message_id)
        await callback.answer(alert_text, show_alert=True)
        # В случае ошибки просто обновляем текущее отображение
        await _display_help_message_details(callback, state, message_id, lang)
