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
    delete_help_message,
    get_all_help_messages
)
from .admin_filters import IsAdmin
from .admin_states import AdminStates
from localization import get_localized_message

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

    active_message = await get_active_help_message_from_db()

    current_active_status_text = get_localized_message("admin_help_no_active_message", lang)
    if active_message:
        # Экранируем HTML-теги для безопасного отображения
        escaped_text = html.escape(active_message.message_text[:100])  # Предпросмотр 100 символов
        if len(active_message.message_text) > 100:
            escaped_text += "..."
        # Используем существующий ключ admin_help_active_message_status и добавляем предпросмотр текста
        current_active_status_text = get_localized_message("admin_help_active_message_status", lang).format(
            message_id=active_message.id
        ) + f"\n<i>{get_localized_message('admin_help_preview_prefix', lang)}</i>: {escaped_text}"

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_create_help_message", lang),
                                      callback_data="admin_add_help_message"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_manage_existing_help_messages", lang),
                                      callback_data="admin_view_all_help_messages"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang),
                                      callback_data="admin_panel_back"))
    keyboard.adjust(1)

    menu_text = get_localized_message("admin_help_manage_title", lang).format(
        current_active_status=current_active_status_text)

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(menu_text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.HTML)


async def _display_all_help_messages(
        update_object: Union[Message, CallbackQuery],
        lang: str
):
    """
    Отображает список всех сообщений помощи с кнопками для активации/удаления.
    """
    user_id = update_object.from_user.id
    logger.info(f"Админ {user_id} просматривает все сообщения помощи.")

    all_messages = await get_all_help_messages()

    # Только заголовок списка сообщений
    messages_list_text = get_localized_message("admin_help_all_messages_title", lang) + "\n\n"
    keyboard = InlineKeyboardBuilder()

    if all_messages:
        for msg in all_messages:
            status_emoji = "✅" if msg.is_active else "⚪"
            # Экранируем HTML-теги для безопасного отображения
            # Убираем HTML-теги из текста кнопки, так как они не поддерживаются
            escaped_text = html.escape(msg.message_text[:50])
            if len(msg.message_text) > 50:
                escaped_text += "..."

            # Измененный текст кнопки: ID: [message_id] | [message_text] (без HTML-тегов)
            button_text = f"ID: {msg.id} | {escaped_text}"  # <-- ИЗМЕНЕНО: Убраны теги <code>

            keyboard.row(
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"admin_select_help_message:{msg.id}"
                )
            )
        keyboard.adjust(1)
    else:
        messages_list_text += get_localized_message("admin_help_no_saved_messages", lang)

    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang),
                                      callback_data="admin_manage_help_messages"))

    if isinstance(update_object, Message):
        await update_object.answer(messages_list_text, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(messages_list_text, reply_markup=keyboard.as_markup(),
                                              parse_mode=ParseMode.HTML)


# --- Хэндлеры для меню управления сообщениями помощи ---

@router.callback_query(F.data == "admin_manage_help_messages", IsAdmin())
async def admin_manage_help_messages_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса для отображения главного меню управления сообщениями помощи.
    Показывает текущее активное сообщение (если есть) и кнопки действий.
    """
    logger.info(f"Админ {callback.from_user.id} вошел в управление сообщениями помощи.")
    await state.clear()
    await _display_help_messages_menu(callback, state, lang)


@router.callback_query(F.data == "admin_add_help_message", IsAdmin())
async def admin_add_help_message_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса для начала добавления нового сообщения помощи.
    Переводит админа в состояние ожидания текста.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} начал добавление нового сообщения помощи.")
    await state.set_state(AdminStates.waiting_for_help_message_text)
    await callback.message.edit_text(
        get_localized_message("admin_help_prompt_new_message_text", lang),
        reply_markup=InlineKeyboardBuilder().row(
            InlineKeyboardButton(text=get_localized_message("button_cancel", lang),
                                 callback_data="admin_manage_help_messages")
        ).as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_for_help_message_text), IsAdmin())
async def admin_process_new_help_message_text(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает введенный админом текст нового сообщения помощи.
    Сохраняет его в БД и предлагает сделать активным.
    """
    user_id = message.from_user.id
    message_text = message.text.strip()
    logger.info(f"Админ {user_id} ввел текст сообщения помощи.")

    if not message_text:
        await message.answer(get_localized_message("admin_help_prompt_new_message_text", lang),
                             parse_mode=ParseMode.HTML)
        return

    # Добавляем сообщение в БД, по умолчанию неактивное
    new_message = await add_help_message(message_text, is_active=False)

    # Сохраняем ID нового сообщения в FSM для дальнейших действий
    await state.update_data(new_help_message_id=new_message.id)
    await state.set_state(AdminStates.waiting_for_help_message_selection)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_save_and_activate", lang),
                                      callback_data=f"admin_set_active_help_message:{new_message.id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_save_only", lang),
                                      callback_data=f"admin_save_only_help_message:{new_message.id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang),
                                      callback_data="admin_manage_help_messages"))
    keyboard.adjust(1)

    await message.answer(
        get_localized_message("admin_help_message_added_success", lang).format(message_id=new_message.id),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data.startswith("admin_save_only_help_message:"), IsAdmin())
async def admin_save_only_help_message(
        callback: CallbackQuery,
        lang: str
):
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для сохранения сообщения помощи без активации: {callback.data}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Админ {user_id} сохраняет сообщение помощи ID: {message_id} без активации.")
    alert_text = get_localized_message("admin_help_saved_only", lang).format(message_id=message_id)
    await callback.answer(alert_text, show_alert=True)
    await _display_all_help_messages(callback, lang)


@router.callback_query(F.data == "admin_view_all_help_messages", IsAdmin())
async def admin_view_all_help_messages_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса для просмотра всех сообщений помощи.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} просматривает все сообщения помощи.")
    await state.clear()
    await _display_all_help_messages(callback, lang)


@router.callback_query(F.data.startswith("admin_select_help_message:"), IsAdmin())
async def admin_select_help_message(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обработчик callback-запроса для выбора конкретного сообщения помощи из списка.
    Показывает опции: сделать активным или удалить.
    """
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для выбора сообщения помощи: {callback.data}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Админ {user_id} выбрал сообщение помощи ID: {message_id}.")
    await state.update_data(selected_help_message_id=message_id)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_activate_help_message", lang),
                                      callback_data=f"admin_set_active_help_message:{message_id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_delete", lang),
                                      callback_data=f"admin_confirm_delete_help_message:{message_id}"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_messages_list", lang),
                                      callback_data="admin_view_all_help_messages"))
    keyboard.adjust(1)

    selected_message_obj = await get_help_message_by_id(message_id)
    message_content_text = ""
    if selected_message_obj:
        # Теперь выводим сам текст сообщения, без дополнительной метки "admin_help_message_text_label"
        message_content_text = get_localized_message("admin_help_message_details_title", lang).format(
            message_id=message_id) + "\n\n" + \
                               f"<code>{html.escape(selected_message_obj.message_text)}</code>\n\n" + \
                               get_localized_message("admin_help_message_created_at_label",
                                                     lang) + f": {selected_message_obj.created_at.strftime('%d.%m.%Y %H:%M')}\n"
        if selected_message_obj.updated_at:
            message_content_text += get_localized_message("admin_help_message_updated_at_label",
                                                          lang) + f": {selected_message_obj.updated_at.strftime('%d.%m.%Y %H:%M')}\n"
        message_content_text += get_localized_message("admin_help_what_to_do", lang)
    else:
        message_content_text = get_localized_message("admin_help_message_not_found", lang).format(message_id=message_id)

    await callback.message.edit_text(
        message_content_text,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_set_active_help_message:"), IsAdmin())
async def admin_set_active_help_message_confirmed(
        callback: CallbackQuery,
        lang: str
):
    """
    Обработчик callback-запроса: устанавливает выбранное сообщение помощи активным.
    """
    user_id = callback.from_user.id
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для установки активного сообщения: {callback.data}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Админ {user_id} устанавливает сообщение помощи ID: {message_id} активным.")

    success = await set_active_help_message(message_id)

    if success:
        alert_text = get_localized_message("admin_help_activated_success", lang).format(message_id=message_id)
        await callback.message.edit_text(
            alert_text,
            parse_mode=ParseMode.HTML
        )
        await callback.answer(alert_text, show_alert=True)
    else:
        alert_text = get_localized_message("admin_help_activate_failed", lang).format(message_id=message_id)
        await callback.message.edit_text(
            alert_text,
            parse_mode=ParseMode.HTML
        )
        await callback.answer(alert_text, show_alert=True)

    await _display_all_help_messages(callback, lang)


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
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Админ {user_id} запросил подтверждение удаления сообщения помощи ID: {message_id}.")

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_yes_delete", lang),
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
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
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
        await callback.message.edit_text(
            alert_text,
            parse_mode=ParseMode.HTML
        )
        await callback.answer(alert_text, show_alert=True)

    await _display_all_help_messages(callback, lang)
