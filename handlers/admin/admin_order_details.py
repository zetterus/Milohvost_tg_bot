import logging
import urllib.parse

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hbold, hcode
from aiogram.fsm.context import FSMContext

from config import ORDER_STATUS_MAP
from db import get_order_by_id, update_order_status, update_order_text, delete_order
from .admin_utils import _display_admin_main_menu, _display_orders_paginated
from .admin_filters import IsAdmin
from .admin_states import AdminStates

logger = logging.getLogger(__name__)
router = Router()  # Локальный роутер для этого модуля


@router.callback_query(F.data.startswith("view_order_"), IsAdmin())
async def admin_view_order_details_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Заказ #ID" для детального просмотра заказа.
    Показывает подробную информацию о заказе и кнопки для изменения статуса.
    """
    order_id = int(callback.data.split("_")[2])
    logger.info(f"Админ {callback.from_user.id} просматривает детали заказа ID {order_id}.")

    order = await get_order_by_id(order_id)

    if order:
        display_status = ORDER_STATUS_MAP.get(order.status, order.status)
        order_details_text = (
            f"{hbold('Детали заказа № ')}{hbold(str(order.id))}\n\n"
            f"{hbold('Пользователь:')} {hbold(order.username or 'N/A')} ({order.user_id})\n"
            f"{hbold('Статус:')} {hbold(display_status)}\n"
            f"{hbold('Текст заказа:')}\n{hcode(order.order_text)}\n"
            f"{hbold('ФИО:')} {order.full_name or 'Не указано'}\n"
            f"{hbold('Адрес доставки:')} {order.delivery_address or 'Не указан'}\n"
            f"{hbold('Метод оплаты:')} {order.payment_method or 'Не указан'}\n"
            f"{hbold('Телефон:')} {order.contact_phone or 'Не указан'}\n"
            f"{hbold('Примечания:')} {order.delivery_notes or 'Нет'}\n"
            f"{hbold('Дата создания:')} {order.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
        )

        status_keyboard = InlineKeyboardBuilder()

        # Кнопки смены статуса (остаются)
        for status_key, status_value in ORDER_STATUS_MAP.items():
            if status_key != order.status:
                status_keyboard.add(InlineKeyboardButton(
                    text=f"🔄 {status_value}",
                    callback_data=f"admin_change_status_{order.id}_{status_key}"
                ))
        status_keyboard.adjust(2)  # Adjusts status buttons to 2 per row

        # --- НОВЫЕ КНОПКИ РЕДАКТИРОВАНИЯ И УДАЛЕНИЯ ---
        status_keyboard.row(
            InlineKeyboardButton(
                text="✏️ Редактировать текст заказа",
                callback_data=f"admin_edit_order_text_{order.id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить заказ",
                callback_data=f"admin_confirm_delete_order_{order.id}"  # Запрос подтверждения
            )
        )

        # --- Логика кнопки "Назад к заказам/поиску" ---
        data = await state.get_data()
        current_page = data.get("current_page", 1)
        search_query = data.get("search_query")

        if search_query:  # Если есть поисковый запрос в FSM, возвращаемся к поиску
            encoded_query = urllib.parse.quote_plus(search_query)
            status_keyboard.row(InlineKeyboardButton(
                text="⬅️ Назад к поиску",
                callback_data=f"admin_search_page:{current_page}:{encoded_query}"
            ))
        else:  # Иначе возвращаемся ко всем заказам
            status_keyboard.row(InlineKeyboardButton(
                text="⬅️ Назад к заказам",
                callback_data=f"admin_all_orders_page:{current_page}"
            ))

        await callback.message.edit_text(
            order_details_text,
            reply_markup=status_keyboard.as_markup(),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text("Заказ не найден.", parse_mode="HTML")

    await callback.answer()


@router.callback_query(F.data.startswith("admin_change_status_"), IsAdmin())
async def admin_change_order_status_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    parts = callback.data.split('_')
    if len(parts) < 5:
        await bot.answer_callback_query(callback.id, "Неверный формат данных коллбэка для статуса.",
                                        show_alert=True)  # <--- Используем bot
        return

    try:
        order_id = int(parts[3])
        new_status = parts[4]
    except (ValueError, IndexError):
        await bot.answer_callback_query(callback.id, "Неверный ID заказа или статус.",
                                        show_alert=True)  # <--- Используем bot
        return

    logger.info(f"Админ {callback.from_user.id} меняет статус заказа ID {order_id} на '{new_status}'.")

    updated_order = await update_order_status(order_id, new_status)

    if updated_order:
        display_status = ORDER_STATUS_MAP.get(updated_order.status, updated_order.status)
        await bot.answer_callback_query(callback.id, text=f"Статус заказа №{order_id} изменен на '{display_status}'!",
                                        show_alert=True)  # <--- Используем bot

        # --- НОВЫЙ ПОДХОД: Вместо пересоздания CallbackQuery, заново формируем и редактируем сообщение ---

        order = await get_order_by_id(order_id)  # Получаем актуальные данные заказа
        if not order:
            await bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        text="Ошибка: Обновленный заказ не найден.", parse_mode="HTML")
            return

        order_details_text = (
            f"{hbold('Детали заказа № ')}{hbold(str(order.id))}\n\n"
            f"{hbold('Пользователь:')} {hbold(order.username or 'N/A')} ({order.user_id})\n"
            f"{hbold('Статус:')} {hbold(display_status)}\n"
            f"{hbold('Текст заказа:')}\n{hcode(order.order_text)}\n"
            f"{hbold('ФИО:')} {order.full_name or 'Не указано'}\n"
            f"{hbold('Адрес доставки:')} {order.delivery_address or 'Не указан'}\n"
            f"{hbold('Метод оплаты:')} {order.payment_method or 'Не указан'}\n"
            f"{hbold('Телефон:')} {order.contact_phone or 'Не указан'}\n"
            f"{hbold('Примечания:')} {order.delivery_notes or 'Нет'}\n"
            f"{hbold('Дата создания:')} {order.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
        )

        status_keyboard = InlineKeyboardBuilder()
        for status_key, status_value in ORDER_STATUS_MAP.items():
            if status_key != order.status:
                status_keyboard.add(InlineKeyboardButton(
                    text=f"🔄 {status_value}",
                    callback_data=f"admin_change_status_{order.id}_{status_key}"
                ))
        status_keyboard.adjust(2)

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
        data = await state.get_data()  # Получаем данные из FSM для навигации
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

        await bot.edit_message_text(  # <--- Используем bot.edit_message_text
            chat_id=callback.message.chat.id,
            message_id=callback.message.message_id,
            text=order_details_text,
            reply_markup=status_keyboard.as_markup(),
            parse_mode="HTML"
        )

    else:
        await bot.answer_callback_query(callback.id, "Не удалось изменить статус заказа. Заказ не найден.",
                                        show_alert=True)
        await bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                    text="Ошибка: Заказ не найден.", parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_edit_order_text_"), IsAdmin())
async def admin_edit_order_text_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки "Редактировать текст заказа".
    Запрашивает новый текст и переводит в состояние ожидания ввода.
    """
    order_id = int(callback.data.split("_")[4])
    logger.info(f"Админ {callback.from_user.id} инициировал редактирование текста заказа ID {order_id}.")

    await state.update_data(
        editing_order_id=order_id,
        original_message_id=callback.message.message_id,
        original_chat_id=callback.message.chat.id,
        original_chat_instance=callback.chat_instance  # <-- Добавлено! Сохраняем реальный chat_instance
    )
    await state.set_state(AdminStates.waiting_for_order_text_edit)

    await callback.message.edit_text(
        f"Введите новый текст для заказа №{order_id}:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data=f"view_order_{order_id}")]
        ]),
        parse_mode="HTML"
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

    # Проверяем наличие всех необходимых данных
    if not order_id or not original_message_id or not original_chat_id:
        logger.error(f"Админ {message.from_user.id}: Не найдены все данные для редактирования текста в FSM.")
        await message.answer(
            "Ошибка: Не удалось определить заказ для редактирования. Пожалуйста, попробуйте снова через главное меню.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="В админ-панель", callback_data="admin_panel_back")]
            ]))
        await state.clear()
        return

    new_order_text = message.text.strip()
    logger.info(f"Админ {message.from_user.id} ввел новый текст для заказа ID {order_id}.")

    updated_order = await update_order_text(order_id=order_id, new_text=new_order_text)

    await state.clear()  # Очищаем состояние FSM

    if updated_order:
        await message.answer(f"Текст заказа №{order_id} успешно обновлен!", parse_mode="HTML")

        # --- АЛЬТЕРНАТИВНЫЙ ПОДХОД БЕЗ ФИКШЕНА ---

        # 1. Заново получаем актуальные данные заказа
        order = await get_order_by_id(order_id)
        if not order:  # Если вдруг заказ пропал после обновления (маловероятно, но для надежности)
            await message.answer("Ошибка: Обновленный заказ не найден.", parse_mode="HTML")
            await _display_admin_main_menu(message, state)
            return

        # 2. Формируем текст сообщения с деталями заказа
        display_status = ORDER_STATUS_MAP.get(order.status, order.status)
        order_details_text = (
            f"{hbold('Детали заказа № ')}{hbold(str(order.id))}\n\n"
            f"{hbold('Пользователь:')} {hbold(order.username or 'N/A')} ({order.user_id})\n"
            f"{hbold('Статус:')} {hbold(display_status)}\n"
            f"{hbold('Текст заказа:')}\n{hcode(order.order_text)}\n"
            f"{hbold('ФИО:')} {order.full_name or 'Не указано'}\n"
            f"{hbold('Адрес доставки:')} {order.delivery_address or 'Не указан'}\n"
            f"{hbold('Метод оплаты:')} {order.payment_method or 'Не указан'}\n"
            f"{hbold('Телефон:')} {order.contact_phone or 'Не указан'}\n"
            f"{hbold('Примечания:')} {order.delivery_notes or 'Нет'}\n"
            f"{hbold('Дата создания:')} {order.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
        )

        # 3. Формируем клавиатуру для деталей заказа (аналогично тому, как это делается в admin_view_order_details_callback)
        status_keyboard = InlineKeyboardBuilder()
        for status_key, status_value in ORDER_STATUS_MAP.items():
            if status_key != order.status:
                status_keyboard.add(InlineKeyboardButton(
                    text=f"🔄 {status_value}",
                    callback_data=f"admin_change_status_{order.id}_{status_key}"
                ))
        status_keyboard.adjust(2)

        status_keyboard.row(
            InlineKeyboardButton(
                text="✏️ Редактировать текст заказа",
                callback_data=f"admin_edit_order_text_{order.id}"
            ),
            InlineKeyboardButton(
                text="🗑️ Удалить заказ",
                callback_data=f"admin_confirm_delete_order_{order_id}"
            )
        )

        # Добавляем кнопки навигации (Назад к поиску/заказам)
        state_data_for_navigation = await state.get_data()  # Получаем актуальные данные для навигации
        current_page = state_data_for_navigation.get("current_page", 1)
        search_query = state_data_for_navigation.get("search_query")
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

        # 4. Редактируем исходное сообщение с деталями заказа
        await bot.edit_message_text(
            chat_id=original_chat_id,
            message_id=original_message_id,
            text=order_details_text,
            reply_markup=status_keyboard.as_markup(),
            parse_mode="HTML"
        )
        # --- КОНЕЦ АЛЬТЕРНАТИВНОГО ПОДХОДА ---

    else:
        await message.answer("Не удалось обновить текст заказа. Заказ не найден.", parse_mode="HTML")
        await _display_admin_main_menu(message, state)


@router.callback_query(F.data.startswith("admin_confirm_delete_order_"), IsAdmin())
async def admin_confirm_delete_order_callback(callback: CallbackQuery, state: FSMContext):
    """
    Запрашивает подтверждение удаления заказа.
    """
    order_id = int(callback.data.split("_")[4])
    logger.info(f"Админ {callback.from_user.id} запрашивает подтверждение удаления заказа ID {order_id}.")

    await state.update_data(
        deleting_order_id=order_id,
        original_message_id_for_delete_confirm=callback.message.message_id,
        original_chat_id_for_delete_confirm=callback.message.chat.id,
        original_chat_instance_for_delete_confirm=callback.chat_instance  # <-- Добавлено!
    )

    confirm_keyboard = InlineKeyboardBuilder()
    confirm_keyboard.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"admin_delete_order_{order_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"view_order_{order_id}")
    )

    await callback.message.edit_text(
        f"Вы уверены, что хотите удалить заказ №{order_id}?",
        reply_markup=confirm_keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_order_"), IsAdmin())
async def admin_delete_order_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Выполняет удаление заказа после подтверждения.
    """
    order_id = int(callback.data.split("_")[3])
    logger.info(f"Админ {callback.from_user.id} подтвердил удаление заказа ID {order_id}.")

    deleted = await delete_order(order_id=order_id)

    await state.clear()

    if deleted:
        await bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                    text=f"Заказ №{order_id} успешно удален.", parse_mode="HTML")
        await bot.answer_callback_query(callback.id, text=f"Заказ №{order_id} успешно удален.")

        # Если заказ удален, возвращаемся к списку заказов
        data = await state.get_data()  # Это могут быть старые данные FSM, но они нужны для пагинации
        current_page = data.get("current_page", 1)
        search_query = data.get("search_query")

        await _display_orders_paginated(callback, state, current_page=current_page,
                                        is_search=bool(search_query))
    else:
        await bot.answer_callback_query(callback.id, text="Не удалось удалить заказ. Заказ не найден.",
                                        show_alert=True)

        # --- АЛЬТЕРНАТИВНЫЙ ПОДХОД БЕЗ ФИКШЕНА ДЛЯ СЛУЧАЯ НЕУДАЧИ ---
        data = await state.get_data()
        original_message_id = data.get("original_message_id_for_delete_confirm")
        original_chat_id = data.get("original_chat_id_for_delete_confirm")

        if original_message_id and original_chat_id:
            # Заново получаем данные заказа (он не был удален)
            order = await get_order_by_id(order_id)
            if order:
                display_status = ORDER_STATUS_MAP.get(order.status, order.status)
                order_details_text = (
                    f"{hbold('Детали заказа № ')}{hbold(str(order.id))}\n\n"
                    f"{hbold('Пользователь:')} {hbold(order.username or 'N/A')} ({order.user_id})\n"
                    f"{hbold('Статус:')} {hbold(display_status)}\n"
                    f"{hbold('Текст заказа:')}\n{hcode(order.order_text)}\n"
                    f"{hbold('ФИО:')} {order.full_name or 'Не указано'}\n"
                    f"{hbold('Адрес доставки:')} {order.delivery_address or 'Не указан'}\n"
                    f"{hbold('Метод оплаты:')} {order.payment_method or 'Не указан'}\n"
                    f"{hbold('Телефон:')} {order.contact_phone or 'Не указан'}\n"
                    f"{hbold('Примечания:')} {order.delivery_notes or 'Нет'}\n"
                    f"{hbold('Дата создания:')} {order.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
                )

                status_keyboard = InlineKeyboardBuilder()
                for status_key, status_value in ORDER_STATUS_MAP.items():
                    if status_key != order.status:
                        status_keyboard.add(InlineKeyboardButton(text=f"🔄 {status_value}",
                                                                 callback_data=f"admin_change_status_{order.id}_{status_key}"))
                status_keyboard.adjust(2)
                status_keyboard.row(
                    InlineKeyboardButton(text="✏️ Редактировать текст заказа",
                                         callback_data=f"admin_edit_order_text_{order.id}"),
                    InlineKeyboardButton(text="🗑️ Удалить заказ",
                                         callback_data=f"admin_confirm_delete_order_{order_id}")
                )
                state_data_for_navigation = await state.get_data()
                current_page = state_data_for_navigation.get("current_page", 1)
                search_query = state_data_for_navigation.get("search_query")
                if search_query:
                    encoded_query = urllib.parse.quote_plus(search_query)
                    status_keyboard.row(InlineKeyboardButton(text="⬅️ Назад к поиску",
                                                             callback_data=f"admin_search_page:{current_page}:{encoded_query}"))
                else:
                    status_keyboard.row(InlineKeyboardButton(text="⬅️ Назад к заказам",
                                                             callback_data=f"admin_all_orders_page:{current_page}"))

                await bot.edit_message_text(
                    chat_id=original_chat_id,
                    message_id=original_message_id,
                    text=order_details_text,
                    reply_markup=status_keyboard.as_markup(),
                    parse_mode="HTML"
                )
            else:
                await bot.edit_message_text(chat_id=original_chat_id, message_id=original_message_id,
                                            text="Не удалось удалить заказ. Возвращаюсь в главное меню.",
                                            parse_mode="HTML")
                await _display_admin_main_menu(callback, state)
        else:
            await bot.edit_message_text(chat_id=callback.message.chat.id, message_id=callback.message.message_id,
                                        text="Не удалось удалить заказ. Возвращаюсь в главное меню.",
                                        parse_mode="HTML")
            await _display_admin_main_menu(callback, state)
