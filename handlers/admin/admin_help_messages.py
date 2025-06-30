import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.utils.markdown import hbold, hcode  # hbold и hcode генерируют HTML-разметку (<b> и <code>)
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode  # Для явного указания режима парсинга HTML

# Импорты из вашего проекта
from db import (
    get_active_help_message_from_db,
    add_help_message,
    get_help_message_by_id,
    set_active_help_message,
    delete_help_message,
    get_all_help_messages
)
from .admin_filters import IsAdmin  # Пользовательский фильтр для проверки прав админа
from .admin_states import AdminStates  # FSM-состояния для админ-панели

# Настройка логирования для данного модуля
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
        # Используем hcode для форматирования ID сообщения как кода
        current_active_status = f"✅ Активное сообщение (ID: <code>{active_message.id}</code>)"

    # Создаем инлайн-клавиатуру для меню управления
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="➕ Создать новое сообщение помощи", callback_data="admin_create_help_message"))
    keyboard.row(InlineKeyboardButton(text="📝 Управлять существующими сообщениями",
                                      callback_data="admin_manage_existing_help_messages"))
    keyboard.row(InlineKeyboardButton(text="🔙 В главное меню админа",
                                      callback_data="admin_panel_back"))  # Кнопка возврата в основное меню админа
    keyboard.adjust(1)  # Располагаем кнопки в один столбец

    # Редактируем сообщение, чтобы отобразить меню управления
    await callback.message.edit_text(
        f"<b>Управление сообщениями помощи</b>\n\n"  # Жирный текст заголовка
        f"Текущий статус: {current_active_status}\n\n"
        "Что вы хотите сделать?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML  # Явно указываем HTML-режим для корректного отображения разметки
    )
    await callback.answer()  # Отправляем пустой ответ на callback-запрос, чтобы убрать "часики"


@router.callback_query(F.data == "admin_view_active_help_message", IsAdmin())
async def admin_view_active_help_message_callback(callback: CallbackQuery):
    """
    Обработчик callback-запроса для отображения содержимого текущего активного сообщения помощи.
    """
    active_message = await get_active_help_message_from_db()

    if active_message:
        text_to_display = (
            f"{hbold('Текущее активное сообщение помощи:')}\n\n"
            f"{active_message.message_text}\n\n"  # Текст сообщения помощи (предполагается, что он уже в HTML)
            f"{hbold('ID сообщения:')} {hcode(active_message.id)}\n"
            f"{hbold('Статус:')} {'Активно ✅' if active_message.is_active else 'Неактивно ❌'}\n"
            f"{hbold('Дата создания:')} {active_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}"
        )
    else:
        text_to_display = hbold("Активное сообщение помощи не найдено.")

    # Создаем кнопку для возврата
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))

    # Редактируем сообщение для отображения деталей активного сообщения
    await callback.message.edit_text(
        text_to_display,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML  # Явно указываем HTML-режим
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
        "Введите <b>текст</b> нового сообщения помощи. \n\n"  # Инструкция с HTML-разметкой
        "Вы можете использовать <i>HTML</i> разметку.",  # Подсказка по типу разметки
        parse_mode=ParseMode.HTML  # Явно указываем HTML-режим
    )
    # Устанавливаем FSM-состояние для ожидания текста сообщения
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

    if not help_message_text or not help_message_text.strip():  # Проверяем на пустой текст
        await message.answer(
            "Текст сообщения не может быть пустым. Пожалуйста, введите текст.",
            parse_mode=ParseMode.HTML
        )
        return

    # Временно сохраняем текст в FSMContext для дальнейшего использования
    await state.update_data(new_help_message_text=help_message_text)

    # Создаем инлайн-клавиатуру с вариантами действий
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="Сохранить и сделать активным ✅",
                                      callback_data="admin_save_and_activate_help_message"))
    keyboard.row(
        InlineKeyboardButton(text="Сохранить, но не активировать 📝", callback_data="admin_save_only_help_message"))
    keyboard.row(InlineKeyboardButton(text="Отменить создание ❌", callback_data="admin_cancel_help_message_creation"))
    keyboard.adjust(1)  # Кнопки в один столбец

    # Формируем текст предварительного просмотра
    preview_text = (
        f"<b>Предварительный просмотр сообщения:</b>\n\n"
        f"{help_message_text}\n\n"  # Здесь отображаем введенный текст. Он будет парситься как HTML.
        "Что будем делать с этим сообщением?"
    )

    # Отправляем предварительный просмотр и кнопки
    await message.answer(
        preview_text,
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML  # Явно указываем HTML-режим для предварительного просмотра
    )
    # Состояние не сбрасываем, так как ожидаем выбора админа по кнопкам


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
        await admin_manage_help_messages_callback(callback)  # Возвращаемся в меню управления
        return

    # Добавляем сообщение в БД и сразу делаем его активным
    new_help_msg = await add_help_message(message_text, is_active=True)
    await set_active_help_message(new_help_msg.id)  # Дополнительно убеждаемся, что оно стало активным

    logger.info(f"Админ {callback.from_user.id} сохранил и активировал новое сообщение помощи (ID: {new_help_msg.id}).")
    await callback.message.edit_text(
        f"✅ Сообщение помощи (ID: <code>{new_help_msg.id}</code>) успешно сохранено и активировано.",
        parse_mode=ParseMode.HTML
    )
    await state.clear()  # Сбрасываем FSM-состояние
    await admin_manage_help_messages_callback(callback)  # Возвращаемся в меню управления
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
        await admin_manage_help_messages_callback(callback)  # Возвращаемся в меню управления
        return

    # Добавляем сообщение в БД без активации
    new_help_msg = await add_help_message(message_text, is_active=False)
    logger.info(f"Админ {callback.from_user.id} сохранил новое сообщение помощи без активации (ID: {new_help_msg.id}).")
    await callback.message.edit_text(
        f"📝 Сообщение помощи (ID: <code>{new_help_msg.id}</code>) успешно сохранено, но не активировано.",
        parse_mode=ParseMode.HTML
    )
    await state.clear()  # Сбрасываем FSM-состояние
    await admin_manage_help_messages_callback(callback)  # Возвращаемся в меню управления
    await callback.answer()


@router.callback_query(F.data == "admin_cancel_help_message_creation", IsAdmin())
async def admin_cancel_help_message_creation(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик callback-запроса: отменяет процесс создания нового сообщения помощи.
    """
    logger.info(f"Админ {callback.from_user.id} отменил создание сообщения помощи.")
    await state.clear()  # Сбрасываем FSM-состояние
    await callback.message.edit_text(
        "Создание сообщения помощи отменено.",
        parse_mode=ParseMode.HTML
    )
    await admin_manage_help_messages_callback(callback)  # Возвращаемся в меню управления
    await callback.answer()


# --- Хэндлеры для управления существующими сообщениями помощи ---

@router.callback_query(F.data.startswith("admin_manage_existing_help_messages"), IsAdmin())
async def admin_manage_existing_help_messages(callback: CallbackQuery):
    """
    Обработчик callback-запроса для отображения списка всех существующих сообщений помощи.
    """
    logger.info(f"Админ {callback.from_user.id} запросил управление существующими сообщениями помощи.")
    all_messages = await get_all_help_messages()  # Получаем все сообщения из БД

    if not all_messages:
        # Если сообщений нет, выводим соответствующее сообщение и кнопку возврата
        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))
        await callback.message.edit_text(
            "<b>Сохраненных сообщений помощи пока нет.</b>",
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await callback.answer()
        return

    text_parts = ["<b>Выберите сообщение для активации/удаления:</b>"]
    keyboard = InlineKeyboardBuilder()

    # Создаем кнопку для каждого сообщения
    for msg in all_messages:
        status_emoji = "✅" if msg.is_active else "❌"
        # Обрезаем текст сообщения для кнопки, чтобы оно не было слишком длинным
        display_text = msg.message_text[:50].replace('\n', ' ') + "..." if len(
            msg.message_text) > 50 else msg.message_text.replace('\n', ' ')
        button_text = f"{status_emoji} ID: {msg.id} - {display_text}"
        keyboard.row(InlineKeyboardButton(text=button_text, callback_data=f"admin_select_help_message:{msg.id}"))

    # Добавляем кнопку возврата в конце списка
    keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))
    keyboard.adjust(1)  # Кнопки в один столбец

    await callback.message.edit_text(
        "\n".join(text_parts),
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
        await admin_manage_existing_help_messages(callback)  # Возвращаемся к списку, если сообщение не найдено
        await callback.answer()
        return

    # Формируем текст с деталями сообщения
    text_to_display = (
        f"<b>Детали сообщения помощи:</b>\n\n"
        f"{selected_message.message_text}\n\n"  # Текст сообщения, который админ ввел (предполагается HTML)
        f"<b>ID сообщения:</b> <code>{selected_message.id}</code>\n"
        f"<b>Статус:</b> {'Активно ✅' if selected_message.is_active else 'Неактивно ❌'}\n"
        f"<b>Дата создания:</b> {selected_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"<b>Последнее изменение:</b> {selected_message.updated_at.strftime('%d.%m.%Y %H:%M:%S')}"
    )

    # Создаем инлайн-клавиатуру с действиями
    keyboard = InlineKeyboardBuilder()
    # Если сообщение не активно, добавляем кнопку активации
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
        parse_mode=ParseMode.HTML  # Явно указываем HTML-режим
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
            f"✅ Сообщение ID: <code>{activated_message.id}</code> успешно активировано.",
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось активировать сообщение. Возможно, оно уже удалено.",
            parse_mode=ParseMode.HTML
        )
    await admin_manage_existing_help_messages(callback)  # Возвращаемся к списку сообщений
    await callback.answer()


@router.callback_query(F.data.startswith("admin_confirm_delete_help_message:"), IsAdmin())
async def admin_confirm_delete_help_message(callback: CallbackQuery):
    """
    Обработчик callback-запроса: запрашивает подтверждение удаления сообщения помощи
    для предотвращения случайного удаления.
    """
    message_id = int(callback.data.split(":")[1])
    logger.info(f"Админ {callback.from_user.id} запросил подтверждение удаления сообщения помощи ID: {message_id}.")

    # Создаем клавиатуру с кнопками подтверждения/отмены
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✅ Подтвердить удаление", callback_data=f"admin_delete_help_message:{message_id}"))
    keyboard.row(InlineKeyboardButton(text="❌ Отмена",
                                      callback_data=f"admin_select_help_message:{message_id}"))  # Возврат к деталям сообщения
    keyboard.adjust(1)

    await callback.message.edit_text(
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

    success = await delete_help_message(message_id)  # Вызываем функцию удаления из БД

    if success:
        await callback.message.edit_text(
            f"🗑️ Сообщение ID: <code>{message_id}</code> успешно удалено.",
            parse_mode=ParseMode.HTML
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось удалить сообщение. Возможно, оно уже отсутствует.",
            parse_mode=ParseMode.HTML
        )
    await admin_manage_existing_help_messages(callback)  # Возвращаемся к списку сообщений
    await callback.answer()
