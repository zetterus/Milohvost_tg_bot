import logging
import urllib.parse
import html

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext

from config import ORDER_STATUS_MAP
from db import get_order_by_id, update_order_status, update_order_text, delete_order
from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from .admin_states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


# --- Вспомогательная функция для формирования деталей заказа и клавиатуры ---
async def _build_order_details_and_keyboard(order_id: int, state: FSMContext) -> tuple[
    str, InlineKeyboardMarkup | None]:
    """
    Формирует текст с деталями заказа и соответствующую инлайн-клавиатуру.
    Используется для предотвращения дублирования кода.
    """
    order = await get_order_by_id(order_id)
    if not order:
        return "Заказ не найден.", None

    display_status = ORDER_STATUS_MAP.get(order.status, order.status)

    # ВАЖНО: Экранируем пользовательский ввод, чтобы избежать XSS-уязвимостей
    # Текст заказа, ФИО, адрес и т.д. могут содержать HTML-теги.
    escaped_order_text = html.escape(order.order_text)
    escaped_full_name = html.escape(order.full_name or 'Не указано')
    escaped_delivery_address = html.escape(order.delivery_address or 'Не указан')
    escaped_payment_method = html.escape(order.payment_method or 'Не указан')
    escaped_contact_phone = html.escape(order.contact_phone or 'Не указан')
    escaped_delivery_notes = html.escape(order.delivery_notes or 'Нет')

    # Заменяем hbold и hcode на HTML-теги
    order_details_text = (
        f"<b>Детали заказа № {order.id}</b>\n\n"
        f"<b>Пользователь:</b> <b>{order.username or 'N/A'}</b> ({order.user_id})\n"
        f"<b>Статус:</b> <b>{display_status}</b>\n"
        f"<b>Текст заказа:</b>\n<code>{escaped_order_text}</code>\n"
        f"<b>ФИО:</b> {escaped_full_name}\n"
        f"<b>Адрес доставки:</b> {escaped_delivery_address}\n"
        f"<b>Метод оплаты:</b> {escaped_payment_method}\n"
        f"<b>Телефон:</b> {escaped_contact_phone}\n"
        f"<b>Примечания:</b> {escaped_delivery_notes}\n"
        f"<b>Дата создания:</b> {order.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
    )

    status_keyboard = InlineKeyboardBuilder()

    # Кнопки смены статуса
    for status_key, status_value in ORDER_STATUS_MAP.items():
        if status_key != order.status:
            status_keyboard.add(InlineKeyboardButton(
                text=f"🔄 {status_value}",
                callback_data=f"admin_change_status_{order.id}_{status_key}"
            ))
    status_keyboard.adjust(2)

    # Кнопки редактирования и удаления
    status_keyboard.row(
        InlineKeyboardButton(
            text="✏️ Редактировать текст заказа",
            callback_data=f"admin_edit_order_text_{order.id}"
        ),
        InlineKeyboardButton(
            text="🗑️ Удалить заказ",
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
            text="⬅️ Назад к поиску",
            callback_data=f"admin_search_page:{current_page}:{encoded_query}"
        ))
    else:
        status_keyboard.row(InlineKeyboardButton(
            text="⬅️ Назад к заказам",
            callback_data=f"admin_all_orders_page:{current_page}"
        ))

    return order_details_text, status_keyboard.as_markup()


@router.callback_query(F.data.startswith("view_order_"), IsAdmin())
async def admin_view_order_details_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Заказ #ID" для детального просмотра заказа.
    Показывает подробную информацию о заказе и кнопки для изменения статуса.
    """
    order_id = int(callback.data.split("_")[2])
    logger.info(f"Админ {callback.from_user.id} просматривает детали заказа ID {order_id}.")

    order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state)

    await callback.message.edit_text(
        order_details_text,
        reply_markup=keyboard_markup,
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_change_status_"), IsAdmin())
async def admin_change_order_status_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает изменение статуса заказа.
    """
    try:
        # Используем .split('_') с ограничением для безопасности, чтобы избежать ошибок
        # Примечание: F.data.startswith("admin_change_status_") уже отфильтровал начало
        # Мы знаем, что после "admin_change_status_" будет order_id, а затем new_status
        _, _, _, order_id_str, new_status = callback.data.split('_', 4)  # Разделяем на 5 частей
        order_id = int(order_id_str)
    except (ValueError, IndexError):
        logger.error(
            f"Админ {callback.from_user.id}: Неверный формат callback_data для изменения статуса: {callback.data}")
        await bot.answer_callback_query(callback.id, "Ошибка: Неверный формат данных.", show_alert=True)
        return

    logger.info(f"Админ {callback.from_user.id} меняет статус заказа ID {order_id} на '{new_status}'.")

    updated_order = await update_order_status(order_id, new_status)

    if updated_order:
        display_status = ORDER_STATUS_MAP.get(updated_order.status, updated_order.status)
        await bot.answer_callback_query(callback.id, text=f"Статус заказа №{order_id} изменен на '{display_status}'!",
                                        show_alert=True)

        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state)

        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await bot.answer_callback_query(callback.id, "Не удалось изменить статус заказа. Заказ не найден.",
                                        show_alert=True)
        # Если заказ не найден, пытаемся обновить текущее сообщение, чтобы показать ошибку
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text="Ошибка: Заказ не найден или не удалось обновить статус.",
            parse_mode=ParseMode.HTML
        )


@router.callback_query(F.data.startswith("admin_edit_order_text_"), IsAdmin())
async def admin_edit_order_text_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Редактировать текст заказа".
    Запрашивает новый текст и переводит в состояние ожидания ввода.
    """
    try:
        # Используем split('_') с ограничением
        order_id = int(callback.data.split("_", 4)[4])  # admin_edit_order_text_ORDER_ID
    except (ValueError, IndexError):
        logger.error(
            f"Админ {callback.from_user.id}: Неверный формат callback_data для редактирования текста: {callback.data}")
        await callback.answer("Ошибка: Неверный формат данных.", show_alert=True)
        return

    logger.info(f"Админ {callback.from_user.id} инициировал редактирование текста заказа ID {order_id}.")

    await state.update_data(
        editing_order_id=order_id,
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
    )
    await state.set_state(AdminStates.waiting_for_order_text_edit)

    await callback.message.edit_text(
        f"Введите новый текст для заказа №{order_id}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data=f"view_order_{order_id}")]
        ]),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.message(StateFilter(AdminStates.waiting_for_order_text_edit), IsAdmin())
async def admin_process_new_order_text(message: Message, state: FSMContext, bot: Bot):
    """
    Обрабатывает ввод нового текста для заказа.
    Обновляет заказ в базе данных и возвращается к деталям заказа,
    редактируя предыдущее сообщение.
    """
    data = await state.get_data()
    order_id = data.get("editing_order_id")
    original_message_id = data.get("original_message_id")
    original_chat_id = data.get("original_chat_id")

    if not all([order_id, original_message_id, original_chat_id]):
        logger.error(f"Админ {message.from_user.id}: Не найдены все данные для редактирования текста в FSM.")
        await message.answer(
            "Ошибка: Не удалось определить заказ для редактирования. Пожалуйста, попробуйте снова через главное меню.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel_back")]
            ]),
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return

    new_order_text = message.text.strip()
    logger.info(f"Админ {message.from_user.id} ввел новый текст для заказа ID {order_id}.")

    updated_order = await update_order_text(order_id=order_id, new_text=new_order_text)

    await state.clear()

    if updated_order:
        # # Отправляем подтверждение в чат админа
        # await message.answer(f"Текст заказа №{order_id} успешно обновлен!", parse_mode=ParseMode.HTML)

        # Редактируем исходное сообщение с деталями заказа
        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state)
        await bot.edit_message_text(
            chat_id=original_chat_id,
            message_id=original_message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer("Не удалось обновить текст заказа. Заказ не найден.", parse_mode=ParseMode.HTML)
        # В случае неудачи, пытаемся обновить исходное сообщение, чтобы оно не осталось в состоянии редактирования
        # Если _build_order_details_and_keyboard вернет текст "Заказ не найден.", это будет корректно
        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state)
        await bot.edit_message_text(
            chat_id=original_chat_id,
            message_id=original_message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )


@router.callback_query(F.data.startswith("admin_confirm_delete_order_"), IsAdmin())
async def admin_confirm_delete_order_callback(callback: CallbackQuery, state: FSMContext):
    """
    Запрашивает подтверждение удаления заказа.
    """
    try:
        # Используем split('_') с ограничением
        order_id = int(callback.data.split("_", 4)[4])  # admin_confirm_delete_order_ORDER_ID
    except (ValueError, IndexError):
        logger.error(
            f"Админ {callback.from_user.id}: Неверный формат callback_data для подтверждения удаления: {callback.data}")
        await callback.answer("Ошибка: Неверный формат данных.", show_alert=True)
        return

    logger.info(f"Админ {callback.from_user.id} запрашивает подтверждение удаления заказа ID {order_id}.")

    # Сохраняем ID сообщения и чата, чтобы вернуться к нему после подтверждения/отмены
    await state.update_data(
        deleting_order_id=order_id,
        original_message_id_for_delete_confirm=callback.message.message_id,
        original_chat_id_for_delete_confirm=callback.message.chat.id,
    )

    confirm_keyboard = InlineKeyboardBuilder()
    confirm_keyboard.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_delete_order_{order_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_order_{order_id}")
    )

    await callback.message.edit_text(
        f"Вы уверены, что хотите удалить заказ №{order_id}?",
        reply_markup=confirm_keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_order_"), IsAdmin())
async def admin_delete_order_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Выполняет удаление заказа после подтверждения.
    """
    try:
        # Используем split('_') с ограничением
        order_id = int(callback.data.split("_", 3)[3])  # admin_delete_order_ORDER_ID
    except (ValueError, IndexError):
        logger.error(f"Админ {callback.from_user.id}: Неверный формат callback_data для удаления: {callback.data}")
        await bot.answer_callback_query(callback.id, "Ошибка: Неверный формат данных.", show_alert=True)
        return

    logger.info(f"Админ {callback.from_user.id} подтвердил удаление заказа ID {order_id}.")

    deleted = await delete_order(order_id=order_id)
    await state.clear()  # Очищаем состояние FSM, так как заказ удален, и контекст больше не нужен

    if deleted:
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=f"Заказ №{order_id} успешно удален.",
            parse_mode=ParseMode.HTML
        )
        await bot.answer_callback_query(callback.id, text=f"Заказ №{order_id} успешно удален.")

        # Возвращаемся к списку заказов после удаления
        # Здесь мы не можем полагаться на старые FSM данные для current_page/search_query,
        # так как state.clear() был вызван.
        # Если вы хотите сохранить пагинацию, вам нужно передавать эти данные через callback_data
        # или переосмыслить очистку состояния.
        # Для простоты, пока просто вернемся в главное меню админа или на первую страницу заказов.
        await _display_orders_paginated(callback, state, current_page=1, is_search=False)
    else:
        await bot.answer_callback_query(callback.id, text="Не удалось удалить заказ. Заказ не найден.", show_alert=True)
        # В случае неудачи, пытаемся обновить исходное сообщение, чтобы оно не осталось в состоянии редактирования
        # Если _build_order_details_and_keyboard вернет текст "Заказ не найден.", это будет корректно
        order_details_text, keyboard_markup = await _build_order_details_and_keyboard(order_id, state)
        await bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=order_details_text,
            reply_markup=keyboard_markup,
            parse_mode=ParseMode.HTML
        )
