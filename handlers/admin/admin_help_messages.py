import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from db import (
    get_active_help_message_from_db,
    add_help_message,
    get_help_message_by_id,
    set_active_help_message,
    delete_help_message,
    get_all_help_messages
)
from .admin_filters import IsAdmin
from .admin_states import AdminStates
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


# --- Хэндлеры для меню управления сообщениями помощи ---

@router.callback_query(F.data == "admin_manage_help_messages", IsAdmin())
async def admin_manage_help_messages_callback(
        callback: CallbackQuery,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса для отображения главного меню управления сообщениями помощи.
    Показывает текущее активное сообщение (если есть) и кнопки действий.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} вошел в управление сообщениями помощи.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    active_message = await get_active_help_message_from_db()

    # Локализованный статус активного сообщения
    current_active_status_text = get_localized_message("admin_help_no_active_message", lang)
    if active_message:
        current_active_status_text = get_localized_message("admin_help_active_message_status", lang).format(
            message_id=active_message.id
        )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text=get_localized_message("admin_button_create_help_message", lang),
                             callback_data="admin_create_help_message"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_manage_existing_help_messages", lang),
                                      callback_data="admin_manage_existing_help_messages"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang),
                                      callback_data="admin_panel_back"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        get_localized_message("admin_help_manage_title", lang).format(
            current_active_status=current_active_status_text
        ),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data == "admin_view_active_help_message", IsAdmin())
async def admin_view_active_help_message_callback(
        callback: CallbackQuery,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса для отображения содержимого текущего активного сообщения помощи.
    """
    # user_id = callback.from_user.id
    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    active_message = await get_active_help_message_from_db()

    if active_message:
        # Локализованные статусы "Активно" / "Неактивно"
        status_text = get_localized_message("admin_help_status_active", lang) if active_message.is_active else \
            get_localized_message("admin_help_status_inactive", lang)

        text_to_display = (
                get_localized_message("admin_help_active_message_title", lang) + "\n\n" +
                f"{active_message.message_text}\n\n"
                f"<b>{get_localized_message('admin_help_message_id_label', lang)}:</b> <code>{active_message.id}</code>\n" +
                f"<b>{get_localized_message('admin_help_message_status_label', lang)}:</b> {status_text}\n" +
                f"<b>{get_localized_message('admin_help_message_created_at_label', lang)}:</b> {active_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}"
        )
    else:
        text_to_display = get_localized_message("admin_help_active_message_not_found", lang)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_help_management", lang),
                                      callback_data="admin_manage_help_messages"))

    await callback.message.edit_text(
        text_to_display,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


# --- Хэндлеры для создания нового сообщения помощи ---

@router.callback_query(F.data == "admin_create_help_message", IsAdmin())
async def admin_create_help_message_start(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Начинает процесс создания нового сообщения помощи.
    Переводит админа в FSM-состояние ожидания текста.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} начал создание нового сообщения помощи.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    await callback.message.edit_text(
        get_localized_message("admin_help_prompt_new_message_text", lang),
        parse_mode=ParseMode.HTML
    )
    await state.set_state(AdminStates.waiting_for_help_message_text)
    await callback.answer()


@router.message(AdminStates.waiting_for_help_message_text, IsAdmin())
async def admin_process_new_help_message_text(
        message: Message,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Принимает введенный админом текст сообщения помощи.
    Отображает предварительный просмотр и предлагает варианты сохранения/отмены.
    """
    user_id = message.from_user.id
    help_message_text = message.text
    logger.info(f"Админ {user_id} ввел текст сообщения помощи.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    if not help_message_text or not help_message_text.strip():
        await message.answer(
            get_localized_message("admin_help_empty_message_error", lang),
            parse_mode=ParseMode.HTML
        )
        return

    await state.update_data(new_help_message_text=help_message_text)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_save_and_activate", lang),
                                      callback_data="admin_save_and_activate_help_message"))
    keyboard.row(
        InlineKeyboardButton(text=get_localized_message("admin_button_save_only", lang),
                             callback_data="admin_save_only_help_message"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_cancel_creation", lang),
                                      callback_data="admin_cancel_help_message_creation"))
    keyboard.adjust(1)

    preview_text = (
            get_localized_message("admin_help_preview_title", lang) + "\n\n" +
            f"{help_message_text}\n\n" +
            get_localized_message("admin_help_what_to_do", lang)
    )

    await message.answer(
        preview_text,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "admin_save_and_activate_help_message", IsAdmin())
async def admin_save_and_activate_help_message(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса: сохраняет новое сообщение помощи в БД и делает его активным.
    """
    user_id = callback.from_user.id
    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    user_data = await state.get_data()
    message_text = user_data.get("new_help_message_text")

    if not message_text:
        await callback.message.edit_text(
            get_localized_message("admin_help_error_text_not_found", lang),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        # Передаем storage и storage_key
        await admin_manage_help_messages_callback(callback, storage=storage, storage_key=storage_key)
        return

    new_help_msg = await add_help_message(message_text, is_active=True)
    await set_active_help_message(new_help_msg.id)

    logger.info(f"Админ {user_id} сохранил и активировал новое сообщение помощи (ID: {new_help_msg.id}).")
    await callback.message.edit_text(
        get_localized_message("admin_help_saved_and_activated", lang).format(message_id=new_help_msg.id),
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    # Передаем storage и storage_key
    await admin_manage_help_messages_callback(callback, storage=storage, storage_key=storage_key)
    await callback.answer()


@router.callback_query(F.data == "admin_save_only_help_message", IsAdmin())
async def admin_save_only_help_message(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса: сохраняет новое сообщение помощи в БД, но не делает его активным.
    """
    user_id = callback.from_user.id
    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    user_data = await state.get_data()
    message_text = user_data.get("new_help_message_text")

    if not message_text:
        await callback.message.edit_text(
            get_localized_message("admin_help_error_text_not_found", lang),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        # Передаем storage и storage_key
        await admin_manage_help_messages_callback(callback, storage=storage, storage_key=storage_key)
        return

    new_help_msg = await add_help_message(message_text, is_active=False)
    logger.info(f"Админ {user_id} сохранил новое сообщение помощи без активации (ID: {new_help_msg.id}).")
    await callback.message.edit_text(
        get_localized_message("admin_help_saved_only", lang).format(message_id=new_help_msg.id),
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    # Передаем storage и storage_key
    await admin_manage_help_messages_callback(callback, storage=storage, storage_key=storage_key)
    await callback.answer()


@router.callback_query(F.data == "admin_cancel_help_message_creation", IsAdmin())
async def admin_cancel_help_message_creation(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса: отменяет процесс создания нового сообщения помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} отменил создание сообщения помощи.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    await state.clear()
    await callback.message.edit_text(
        get_localized_message("admin_help_creation_cancelled", lang),
        parse_mode=ParseMode.HTML
    )
    # Передаем storage и storage_key
    await admin_manage_help_messages_callback(callback, storage=storage, storage_key=storage_key)
    await callback.answer()


# --- Хэндлеры для управления существующими сообщениями помощи ---

@router.callback_query(F.data.startswith("admin_manage_existing_help_messages"), IsAdmin())
async def admin_manage_existing_help_messages(
        callback: CallbackQuery,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса для отображения списка всех существующих сообщений помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} запросил управление существующими сообщениями помощи.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    all_messages = await get_all_help_messages()

    if not all_messages:
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_help_management", lang),
                                          callback_data="admin_manage_help_messages"))
        await callback.message.edit_text(
            get_localized_message("admin_help_no_saved_messages", lang),
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardBuilder()

    for msg in all_messages:
        status_emoji = "✅" if msg.is_active else "❌"
        # Обрезаем текст сообщения для кнопки, чтобы оно не было слишком длинным
        display_text = msg.message_text.replace('\n', ' ')
        if len(display_text) > 50:
            display_text = display_text[:50] + "..."
        button_text = f"{status_emoji} ID: {msg.id} - {display_text}"
        keyboard.row(InlineKeyboardButton(text=button_text, callback_data=f"admin_select_help_message:{msg.id}"))

    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_help_management", lang),
                                      callback_data="admin_manage_help_messages"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        get_localized_message("admin_help_select_message_prompt", lang),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_select_help_message:"), IsAdmin())
async def admin_select_help_message(
        callback: CallbackQuery,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса: отображает детали выбранного сообщения помощи
    и предлагает действия (активировать/удалить).
    """
    user_id = callback.from_user.id
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {user_id} выбрал сообщение помощи ID: {message_id}.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    selected_message = await get_help_message_by_id(message_id)

    if not selected_message:
        await callback.message.edit_text(
            get_localized_message("admin_help_message_not_found", lang),
            parse_mode=ParseMode.HTML
        )
        # Передаем storage и storage_key
        await admin_manage_existing_help_messages(callback, storage=storage, storage_key=storage_key)
        await callback.answer()
        return

    # Локализованные статусы "Активно" / "Неактивно"
    status_text = get_localized_message("admin_help_status_active", lang) if selected_message.is_active else \
        get_localized_message("admin_help_status_inactive", lang)

    text_to_display = (
            get_localized_message("admin_help_message_details_title", lang) + "\n\n" +
            f"{selected_message.message_text}\n\n"
            f"<b>{get_localized_message('admin_help_message_id_label', lang)}:</b> <code>{selected_message.id}</code>\n" +
            f"<b>{get_localized_message('admin_help_message_status_label', lang)}:</b> {status_text}\n" +
            f"<b>{get_localized_message('admin_help_message_created_at_label', lang)}:</b> {selected_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n" +
            f"<b>{get_localized_message('admin_help_message_updated_at_label', lang)}:</b> {selected_message.updated_at.strftime('%d.%m.%Y %H:%M:%S')}"
    )

    keyboard = InlineKeyboardBuilder()
    if not selected_message.is_active:
        keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_activate_help_message", lang),
                                          callback_data=f"admin_activate_help_message:{selected_message.id}"))

    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_delete", lang),
                                      callback_data=f"admin_confirm_delete_help_message:{selected_message.id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_messages_list", lang),
                                      callback_data="admin_manage_existing_help_messages"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        text_to_display,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_activate_help_message:"), IsAdmin())
async def admin_activate_help_message(
        callback: CallbackQuery,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса: активирует выбранное сообщение помощи.
    Деактивирует все остальные сообщения.
    """
    user_id = callback.from_user.id
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {user_id} пытается активировать сообщение помощи ID: {message_id}.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    activated_message = await set_active_help_message(message_id)

    if activated_message:
        await callback.message.edit_text(
            get_localized_message("admin_help_activated_success", lang).format(message_id=activated_message.id),
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text(
            get_localized_message("admin_help_activate_failed", lang),
            parse_mode=ParseMode.HTML
        )
    # Передаем storage и storage_key
    await admin_manage_existing_help_messages(callback, storage=storage, storage_key=storage_key)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_delete_help_message:"), IsAdmin())
async def admin_confirm_delete_help_message(
        callback: CallbackQuery,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса: запрашивает подтверждение удаления сообщения помощи
    для предотвращения случайного удаления.
    """
    user_id = callback.from_user.id
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {user_id} запросил подтверждение удаления сообщения помощи ID: {message_id}.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text=get_localized_message("button_yes_delete", lang),
                             callback_data=f"admin_delete_help_message:{message_id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_no_cancel", lang),
                                      callback_data=f"admin_select_help_message:{message_id}"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        get_localized_message("admin_confirm_delete_help_message_prompt", lang).format(message_id=message_id),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_help_message:"), IsAdmin())
async def admin_delete_help_message_confirmed(
        callback: CallbackQuery,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обработчик callback-запроса: удаляет сообщение помощи из БД после подтверждения.
    """
    user_id = callback.from_user.id
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {user_id} подтвердил удаление сообщения помощи ID: {message_id}.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    success = await delete_help_message(message_id)

    if success:
        await callback.message.edit_text(
            get_localized_message("admin_help_deleted_success", lang).format(message_id=message_id),
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text(
            get_localized_message("admin_help_delete_failed", lang),
            parse_mode=ParseMode.HTML
        )
    # Передаем storage и storage_key
    await admin_manage_existing_help_messages(callback, storage=storage, storage_key=storage_key)
    await callback.answer()
