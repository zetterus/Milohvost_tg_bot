import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

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

logger = logging.getLogger(__name__)
router = Router()


# --- Хэндлеры для меню управления сообщениями помощи ---

@router.callback_query(F.data == "admin_manage_help_messages", IsAdmin())
async def admin_manage_help_messages_callback(callback: CallbackQuery):
    """
    Обработчик callback-запроса для отображения главного меню управления сообщениями помощи.
    Показывает текущее активное сообщение (если есть) и кнопки действий.
    """
    logger.info(f"Админ {callback.from_user.id} вошел в управление сообщениями помощи.")

    active_message = await get_active_help_message_from_db()
    current_active_status = "❌ Нет активного сообщения"
    if active_message:
        # Заменяем hcode на HTML-тег
        current_active_status = f"✅ Активное сообщение (ID: <code>{active_message.id}</code>)"

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="➕ Создать новое сообщение помощи", callback_data="admin_create_help_message"))
    keyboard.row(InlineKeyboardButton(text="📝 Управлять существующими сообщениями",
                                      callback_data="admin_manage_existing_help_messages"))
    keyboard.row(InlineKeyboardButton(text="🔙 В главное меню админа", callback_data="admin_panel_back"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        f"<b>Управление сообщениями помощи</b>\n\n"
        f"Текущий статус: {current_active_status}\n\n"
        "Что вы хотите сделать?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data == "admin_view_active_help_message", IsAdmin())
async def admin_view_active_help_message_callback(callback: CallbackQuery):
    """
    Обработчик callback-запроса для отображения содержимого текущего активного сообщения помощи.
    """
    active_message = await get_active_help_message_from_db()

    if active_message:
        # Заменяем hbold и hcode на HTML-теги
        text_to_display = (
            f"<b>Текущее активное сообщение помощи:</b>\n\n"
            f"{active_message.message_text}\n\n"
            f"<b>ID сообщения:</b> <code>{active_message.id}</code>\n"
            f"<b>Статус:</b> {'Активно ✅' if active_message.is_active else 'Неактивно ❌'}\n"
            f"<b>Дата создания:</b> {active_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}"
        )
    else:
        # Заменяем hbold на HTML-тег
        text_to_display = "<b>Активное сообщение помощи не найдено.</b>"

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))

    await callback.message.edit_text(
        text_to_display,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


# --- Хэндлеры для создания нового сообщения помощи ---

@router.callback_query(F.data == "admin_create_help_message", IsAdmin())
async def admin_create_help_message_start(callback: CallbackQuery, state: FSMContext):
    """
    Начинает процесс создания нового сообщения помощи.
    Переводит админа в FSM-состояние ожидания текста.
    """
    logger.info(f"Админ {callback.from_user.id} начал создание нового сообщения помощи.")
    await callback.message.edit_text(
        "Введите <b>текст</b> нового сообщения помощи. \n\n"
        "Вы можете использовать <i>HTML</i> разметку.",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(AdminStates.waiting_for_help_message_text)
    await callback.answer()


@router.message(AdminStates.waiting_for_help_message_text, IsAdmin())
async def admin_process_new_help_message_text(message: Message, state: FSMContext):
    """
    Принимает введенный админом текст сообщения помощи.
    Отображает предварительный просмотр и предлагает варианты сохранения/отмены.
    """
    help_message_text = message.text
    logger.info(f"Админ {message.from_user.id} ввел текст сообщения помощи.")

    if not help_message_text or not help_message_text.strip():
        await message.answer(
            "Текст сообщения не может быть пустым. Пожалуйста, введите текст.",
            parse_mode=ParseMode.HTML
        )
        return

    await state.update_data(new_help_message_text=help_message_text)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="Сохранить и сделать активным ✅",
                                      callback_data="admin_save_and_activate_help_message"))
    keyboard.row(
        InlineKeyboardButton(text="Сохранить, но не активировать 📝", callback_data="admin_save_only_help_message"))
    keyboard.row(InlineKeyboardButton(text="Отменить создание ❌", callback_data="admin_cancel_help_message_creation"))
    keyboard.adjust(1)

    # Заменяем hbold на HTML-теги
    preview_text = (
        f"<b>Предварительный просмотр сообщения:</b>\n\n"
        f"{help_message_text}\n\n"
        "Что будем делать с этим сообщением?"
    )

    await message.answer(
        preview_text,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "admin_save_and_activate_help_message", IsAdmin())
async def admin_save_and_activate_help_message(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик callback-запроса: сохраняет новое сообщение помощи в БД и делает его активным.
    """
    user_data = await state.get_data()
    message_text = user_data.get("new_help_message_text")

    if not message_text:
        await callback.message.edit_text(
            "Ошибка: текст сообщения не найден. Попробуйте еще раз.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        await admin_manage_help_messages_callback(callback)
        return

    new_help_msg = await add_help_message(message_text, is_active=True)
    await set_active_help_message(new_help_msg.id)

    logger.info(f"Админ {callback.from_user.id} сохранил и активировал новое сообщение помощи (ID: {new_help_msg.id}).")
    await callback.message.edit_text(
        # Заменяем hcode на HTML-тег
        f"✅ Сообщение помощи (ID: <code>{new_help_msg.id}</code>) успешно сохранено и активировано.",
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    await admin_manage_help_messages_callback(callback)
    await callback.answer()


@router.callback_query(F.data == "admin_save_only_help_message", IsAdmin())
async def admin_save_only_help_message(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик callback-запроса: сохраняет новое сообщение помощи в БД, но не делает его активным.
    """
    user_data = await state.get_data()
    message_text = user_data.get("new_help_message_text")

    if not message_text:
        await callback.message.edit_text(
            "Ошибка: текст сообщения не найден. Попробуйте еще раз.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        await admin_manage_help_messages_callback(callback)
        return

    new_help_msg = await add_help_message(message_text, is_active=False)
    logger.info(f"Админ {callback.from_user.id} сохранил новое сообщение помощи без активации (ID: {new_help_msg.id}).")
    await callback.message.edit_text(
        # Заменяем hcode на HTML-тег
        f"📝 Сообщение помощи (ID: <code>{new_help_msg.id}</code>) успешно сохранено, но не активировано.",
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    await admin_manage_help_messages_callback(callback)
    await callback.answer()


@router.callback_query(F.data == "admin_cancel_help_message_creation", IsAdmin())
async def admin_cancel_help_message_creation(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик callback-запроса: отменяет процесс создания нового сообщения помощи.
    """
    logger.info(f"Админ {callback.from_user.id} отменил создание сообщения помощи.")
    await state.clear()
    await callback.message.edit_text(
        "Создание сообщения помощи отменено.",
        parse_mode=ParseMode.HTML
    )
    await admin_manage_help_messages_callback(callback)
    await callback.answer()


# --- Хэндлеры для управления существующими сообщениями помощи ---

@router.callback_query(F.data.startswith("admin_manage_existing_help_messages"), IsAdmin())
async def admin_manage_existing_help_messages(callback: CallbackQuery):
    """
    Обработчик callback-запроса для отображения списка всех существующих сообщений помощи.
    """
    logger.info(f"Админ {callback.from_user.id} запросил управление существующими сообщениями помощи.")
    all_messages = await get_all_help_messages()

    if not all_messages:
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))
        await callback.message.edit_text(
            "<b>Сохраненных сообщений помощи пока нет.</b>",
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardBuilder()

    for msg in all_messages:
        status_emoji = "✅" if msg.is_active else "❌"
        # Обрезаем текст сообщения для кнопки, чтобы оно не было слишком длинным
        # Используем replace('\n', ' ') для корректного отображения в одной строке кнопки
        display_text = msg.message_text.replace('\n', ' ')
        if len(display_text) > 50:
            display_text = display_text[:50] + "..."
        button_text = f"{status_emoji} ID: {msg.id} - {display_text}"
        keyboard.row(InlineKeyboardButton(text=button_text, callback_data=f"admin_select_help_message:{msg.id}"))

    keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        "<b>Выберите сообщение для активации/удаления:</b>",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_select_help_message:"), IsAdmin())
async def admin_select_help_message(callback: CallbackQuery):
    """
    Обработчик callback-запроса: отображает детали выбранного сообщения помощи
    и предлагает действия (активировать/удалить).
    """
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {callback.from_user.id} выбрал сообщение помощи ID: {message_id}.")

    selected_message = await get_help_message_by_id(message_id)

    if not selected_message:
        await callback.message.edit_text(
            "<b>Сообщение не найдено.</b>",
            parse_mode=ParseMode.HTML
        )
        await admin_manage_existing_help_messages(callback)
        await callback.answer()
        return

    # Заменяем hbold и hcode на HTML-теги
    text_to_display = (
        f"<b>Детали сообщения помощи:</b>\n\n"
        f"{selected_message.message_text}\n\n"
        f"<b>ID сообщения:</b> <code>{selected_message.id}</code>\n"
        f"<b>Статус:</b> {'Активно ✅' if selected_message.is_active else 'Неактивно ❌'}\n"
        f"<b>Дата создания:</b> {selected_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"<b>Последнее изменение:</b> {selected_message.updated_at.strftime('%d.%m.%Y %H:%M:%S')}"
    )

    keyboard = InlineKeyboardBuilder()
    if not selected_message.is_active:
        keyboard.row(InlineKeyboardButton(text="Сделать активным ✅",
                                          callback_data=f"admin_activate_help_message:{selected_message.id}"))

    keyboard.row(InlineKeyboardButton(text="Удалить 🗑️",
                                      callback_data=f"admin_confirm_delete_help_message:{selected_message.id}"))
    keyboard.row(InlineKeyboardButton(text="🔙 К списку сообщений", callback_data="admin_manage_existing_help_messages"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        text_to_display,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_activate_help_message:"), IsAdmin())
async def admin_activate_help_message(callback: CallbackQuery):
    """
    Обработчик callback-запроса: активирует выбранное сообщение помощи.
    Деактивирует все остальные сообщения.
    """
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {callback.from_user.id} пытается активировать сообщение помощи ID: {message_id}.")

    activated_message = await set_active_help_message(message_id)

    if activated_message:
        await callback.message.edit_text(
            # Заменяем hcode на HTML-тег
            f"✅ Сообщение ID: <code>{activated_message.id}</code> успешно активировано.",
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось активировать сообщение. Возможно, оно уже удалено.",
            parse_mode=ParseMode.HTML
        )
    await admin_manage_existing_help_messages(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_delete_help_message:"), IsAdmin())
async def admin_confirm_delete_help_message(callback: CallbackQuery):
    """
    Обработчик callback-запроса: запрашивает подтверждение удаления сообщения помощи
    для предотвращения случайного удаления.
    """
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {callback.from_user.id} запросил подтверждение удаления сообщения помощи ID: {message_id}.")

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✅ Подтвердить удаление", callback_data=f"admin_delete_help_message:{message_id}"))
    keyboard.row(InlineKeyboardButton(text="❌ Отмена",
                                      callback_data=f"admin_select_help_message:{message_id}"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        # Заменяем hcode на HTML-тег
        f"Вы уверены, что хотите удалить сообщение помощи ID: <code>{message_id}</code>?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_help_message:"), IsAdmin())
async def admin_delete_help_message_confirmed(callback: CallbackQuery):
    """
    Обработчик callback-запроса: удаляет сообщение помощи из БД после подтверждения.
    """
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {callback.from_user.id} подтвердил удаление сообщения помощи ID: {message_id}.")

    success = await delete_help_message(message_id)

    if success:
        await callback.message.edit_text(
            # Заменяем hcode на HTML-тег
            f"🗑️ Сообщение ID: <code>{message_id}</code> успешно удалено.",
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось удалить сообщение. Возможно, оно уже отсутствует.",
            parse_mode=ParseMode.HTML
        )
    await admin_manage_existing_help_messages(callback)
    await callback.answer()
