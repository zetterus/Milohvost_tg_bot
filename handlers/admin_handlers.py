# handlers/admin_handlers.py
import logging
import math
import urllib.parse
from datetime import datetime  # Добавлен импорт datetime для фиктивного CallbackQuery

from aiogram import Router, F, Bot  # Добавлен Bot, так как он может быть передан для mock_callback_query
from aiogram.types import Message, CallbackQuery, Chat  # Добавлен Chat для создания фиктивного Message
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hbold, hcode  # hlink, hitalic (если не используются, можно убрать)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# Константы ORDERS_PER_PAGE и MAX_PREVIEW_TEXT_LENGTH теперь импортируются из config
from config import ADMIN_IDS, ORDER_STATUS_MAP, ORDERS_PER_PAGE, MAX_PREVIEW_TEXT_LENGTH
from db import get_all_orders, get_order_by_id, update_order_status, search_orders, update_order_text, delete_order, get_active_help_message_from_db
from models import Order, HelpMessage  # Убедитесь, что модели доступны

logger = logging.getLogger(__name__)

admin_router = Router()


# Упрощенные состояния
class AdminStates(StatesGroup):
    waiting_for_search_query = State()  # Пользователь вводит поисковый запрос
    waiting_for_order_text_edit = State()  # Пользователь вводит новый текст для заказа


class AdminHandlers:
    """
    Класс для обработки команд и взаимодействий администраторов.
    Используем HTML-форматирование.
    """

    # --- АДМИНСКОЕ МЕНЮ ---
    @staticmethod
    async def _display_admin_main_menu(update_object: Message | CallbackQuery, state: FSMContext):
        """
        Отображает главное меню админ-панели.
        Принимает Message или CallbackQuery и соответствующим образом отправляет/редактирует сообщение.
        Всегда сбрасывает FSM-состояние.
        """
        user_id = update_object.from_user.id

        if user_id not in ADMIN_IDS:
            if isinstance(update_object, Message):
                await update_object.answer("У вас нет прав для доступа к админ-панели.")
            elif isinstance(update_object, CallbackQuery):
                await update_object.answer("У вас нет прав для доступа к админ-панели.", show_alert=True)
            return

        logger.info(f"Админ {user_id} вошел/вернулся в админ-панель.")
        await state.clear()  # Очищаем все данные из FSM, чтобы начать с чистого листа

        # Создаем клавиатуру админ-панели
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Просмотреть все заказы 📋", callback_data="admin_all_orders_start")
        keyboard.button(text="Найти заказы 🔍", callback_data="admin_find_orders")
        keyboard.button(text="Управление помощью 💬", callback_data="admin_manage_help_messages")
        keyboard.adjust(1)

        text = hbold("Добро пожаловать в админ-панель! Выберите действие:")
        reply_markup = keyboard.as_markup()

        if isinstance(update_object, Message):
            await update_object.answer(text, reply_markup=reply_markup, parse_mode="HTML")
        elif isinstance(update_object, CallbackQuery):
            await update_object.answer()
            await update_object.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")

    @admin_router.message(Command("admin"))
    async def admin_command(message: Message, state: FSMContext):
        """
        Обрабатывает команду /admin.
        Проверяет админ-права и отображает главное меню админ-панели.
        Эта команда должна работать из любого состояния.
        """
        await AdminHandlers._display_admin_main_menu(message, state)

    @admin_router.callback_query(F.data == "admin_panel_back")
    async def admin_panel_callbacks(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает коллбэки для возврата в админ-панель из подменю ("admin_panel_back").
        """
        await AdminHandlers._display_admin_main_menu(callback, state)

    # --- ОТОБРАЖЕНИЕ СТРАНИЦЫ СО ВСЕМ ЗАКАЗАМИ/РЕЗУЛЬТАТАМИ ПОИСКА (УНИВЕРСАЛЬНАЯ ФУНКЦИЯ) ---
    @staticmethod
    async def _display_orders_paginated(
            update_object: Message | CallbackQuery,
            state: FSMContext,
            current_page: int,
            is_search: bool = False  # Флаг: это результаты поиска или все заказы
    ):
        user_id = update_object.from_user.id
        if user_id not in ADMIN_IDS:
            if isinstance(update_object, CallbackQuery): await update_object.answer("У вас нет прав.", show_alert=True)
            return

        offset = (current_page - 1) * ORDERS_PER_PAGE
        orders: list[Order] = []
        total_orders: int = 0
        message_context = ""
        query_text = None

        if is_search:
            data = await state.get_data()
            query_text = data.get("search_query")  # Получаем поисковый запрос из FSM
            if not query_text:
                logger.error(
                    f"Админ {user_id}: Попытка пагинации поиска без search_query в FSM. Возврат в админ-панель.")
                text = hbold("Ошибка: поисковый запрос не найден. Начните поиск заново.")
                await AdminHandlers._display_admin_main_menu(update_object, state)
                return

            orders, total_orders = await search_orders(search_query=query_text, offset=offset, limit=ORDERS_PER_PAGE)
            message_context = "результатов поиска"

        else:  # Это просмотр всех заказов
            orders, total_orders = await get_all_orders(offset=offset, limit=ORDERS_PER_PAGE)
            message_context = "всех заказов"

        # Обновляем текущую страницу в FSM, это важно для кнопки "Назад к заказам"
        await state.update_data(current_page=current_page)

        total_pages = math.ceil(total_orders / ORDERS_PER_PAGE) if total_orders > 0 else 1

        # --- Текст сообщения ---
        if query_text:
            header_text = hbold(
                f"Результаты поиска по запросу '{query_text}' (Страница {current_page}/{total_pages}, всего: {total_orders}):")
        else:
            header_text = hbold(
                f"Список {message_context} (Страница {current_page}/{total_pages}, всего: {total_orders}):")

        orders_content_text = header_text + "\n\n"

        if not orders:
            orders_content_text += "Заказов на этой странице нет."

        # --- Кнопки заказов ---
        order_buttons_builder = InlineKeyboardBuilder()
        for order in orders:
            display_status = ORDER_STATUS_MAP.get(order.status, order.status)
            preview_text = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
            if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
                preview_text += "..."

            button_text = f"#{order.id} | {preview_text} | {display_status}"
            order_buttons_builder.add(InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_order_{order.id}"
            ))
        order_buttons_builder.adjust(1)

        # --- Кнопки пагинации ---
        pagination_builder = InlineKeyboardBuilder()

        page_base_prefix = "admin_search_page" if is_search else "admin_all_orders_page"
        encoded_query_text = urllib.parse.quote_plus(query_text) if query_text else ""

        if current_page > 1:
            pagination_builder.button(text="⏮️", callback_data=f"{page_base_prefix}:{1}:{encoded_query_text}")
            if current_page > 5:
                pagination_builder.button(text="◀️5",
                                          callback_data=f"{page_base_prefix}:{max(1, current_page - 5)}:{encoded_query_text}")
            pagination_builder.button(text="◀️",
                                      callback_data=f"{page_base_prefix}:{current_page - 1}:{encoded_query_text}")

        if current_page < total_pages:
            pagination_builder.button(text="▶️",
                                      callback_data=f"{page_base_prefix}:{current_page + 1}:{encoded_query_text}")
            if current_page < total_pages - 4:
                pagination_builder.button(text="▶️5",
                                          callback_data=f"{page_base_prefix}:{min(total_pages, current_page + 5)}:{encoded_query_text}")
            pagination_builder.button(text="⏭️",
                                      callback_data=f"{page_base_prefix}:{total_pages}:{encoded_query_text}")

        # Комбинируем клавиатуры
        final_keyboard = InlineKeyboardBuilder()
        final_keyboard.attach(order_buttons_builder)

        if total_orders > ORDERS_PER_PAGE:
            final_keyboard.row(*pagination_builder.buttons)  # Добавляем кнопки пагинации в один ряд

        final_keyboard.row(InlineKeyboardButton(
            text="🔙 В админ-панель",
            callback_data="admin_panel_back"
        ))

        # Отправляем/редактируем сообщение
        if isinstance(update_object, Message):
            await update_object.answer(orders_content_text, reply_markup=final_keyboard.as_markup(), parse_mode="HTML")
        elif isinstance(update_object, CallbackQuery):
            await update_object.answer()
            await update_object.message.edit_text(orders_content_text, reply_markup=final_keyboard.as_markup(),
                                                  parse_mode="HTML")

    @admin_router.callback_query(F.data.startswith("view_order_"))
    async def admin_view_order_details_callback(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает нажатие кнопки "Заказ #ID" для детального просмотра заказа.
        Показывает подробную информацию о заказе и кнопки для изменения статуса.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

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

    # --- ВЫВОД ВСЕХ ЗАКАЗОВ ---
    @admin_router.callback_query(F.data == "admin_all_orders_start")
    async def admin_start_all_orders_view(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает начальное нажатие кнопки "Просмотреть все заказы".
        Очищает поисковый запрос из FSM и отображает первую страницу всех заказов.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.", show_alert=True)
            return

        logger.info(f"Админ {callback.from_user.id} начал просмотр всех заказов.")
        await state.update_data(search_query=None)  # Очищаем поисковый запрос при просмотре всех заказов

        await AdminHandlers._display_orders_paginated(callback, state, current_page=1, is_search=False)

    @admin_router.callback_query(F.data.startswith("admin_all_orders_page:"))
    async def admin_paginate_all_orders(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает пагинацию для просмотра всех заказов.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.", show_alert=True)
            return

        parts = callback.data.split(':')

        if len(parts) < 2:
            logger.error(f"Неверный формат callback_data для пагинации всех заказов: {callback.data}")
            await callback.answer("Ошибка при обработке страницы.", show_alert=True)
            return

        try:
            current_page = int(parts[1])
        except (ValueError, IndexError):
            logger.error(f"Неверный формат callback_data для пагинации всех заказов: {callback.data}")
            await callback.answer("Ошибка при обработке страницы.", show_alert=True)
            return

        logger.info(f"Админ {callback.from_user.id} переключает страницу всех заказов на {current_page}.")
        await AdminHandlers._display_orders_paginated(callback, state, current_page=current_page, is_search=False)

    # --- ДЕТАЛИ ЗАКАЗА И СМЕНА СТАТУСА ---
    @admin_router.callback_query(F.data.startswith("admin_change_status_"))
    async def admin_change_order_status_callback(callback: CallbackQuery, state: FSMContext):
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        parts = callback.data.split('_')
        if len(parts) < 5:
            await callback.answer("Неверный формат данных коллбэка для статуса.", show_alert=True)
            return

        try:
            order_id = int(parts[3])
            new_status = parts[4]
        except (ValueError, IndexError):
            await callback.answer("Неверный ID заказа или статус.", show_alert=True)
            return

        logger.info(f"Админ {callback.from_user.id} меняет статус заказа ID {order_id} на '{new_status}'.")

        updated_order = await update_order_status(order_id, new_status)

        if updated_order:
            display_status = ORDER_STATUS_MAP.get(updated_order.status, updated_order.status)
            await callback.answer(f"Статус заказа №{order_id} изменен на '{display_status}'!", show_alert=True)

            # Пересоздаем CallbackQuery для повторного отображения деталей заказа
            temp_callback_data = f"view_order_{order_id}"
            temp_callback_query = CallbackQuery(
                id=callback.id,  # Используем оригинальный ID коллбэка, чтобы избежать повторной обработки
                from_user=callback.from_user,
                message=callback.message,  # Это сообщение будет отредактировано
                data=temp_callback_data
            )
            await AdminHandlers.admin_view_order_details_callback(temp_callback_query, state)
        else:
            await callback.answer("Не удалось изменить статус заказа. Заказ не найден.", show_alert=True)
            await callback.message.edit_text("Ошибка: Заказ не найден.", parse_mode="HTML")

    # --- НОВЫЕ ХЕНДЛЕРЫ ДЛЯ РЕДАКТИРОВАНИЯ/УДАЛЕНИЯ ---
    @admin_router.callback_query(F.data.startswith("admin_edit_order_text_"))
    async def admin_edit_order_text_callback(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает нажатие кнопки "Редактировать текст заказа".
        Запрашивает новый текст и переводит в состояние ожидания ввода.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

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

    @admin_router.message(StateFilter(AdminStates.waiting_for_order_text_edit))
    async def admin_process_new_order_text(message: Message, state: FSMContext):
        """
        Обрабатывает ввод нового текста для заказа.
        Обновляет заказ в базе данных и возвращается к деталям заказа,
        редактируя предыдущее сообщение.
        """
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("У вас нет прав для выполнения этой операции.")
            return

        data = await state.get_data()
        order_id = data.get("editing_order_id")
        original_message_id = data.get("original_message_id")
        original_chat_id = data.get("original_chat_id")
        original_chat_instance = data.get("original_chat_instance")

        if not order_id or not original_message_id or not original_chat_id or not original_chat_instance:  # <-- Добавлена проверка
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

        await state.clear()

        if updated_order:
            await message.answer(f"Текст заказа №{order_id} успешно обновлен!", parse_mode="HTML")

            mock_callback_query_message = Message(
                chat=Chat(id=original_chat_id, type="private"),
                message_id=original_message_id,
                date=datetime.now(),
                from_user=message.from_user,
                text="",
                bot=message.bot
            )

            mock_callback_query = CallbackQuery(
                id=f"edit_return_success_{order_id}_{datetime.now().timestamp()}",
                from_user=message.from_user,
                message=mock_callback_query_message,
                data=f"view_order_{order_id}",
                chat_instance=original_chat_instance  # <-- Используем реальный chat_instance
            )
            await AdminHandlers.admin_view_order_details_callback(mock_callback_query, state)
        else:
            await message.answer("Не удалось обновить текст заказа. Заказ не найден.", parse_mode="HTML")
            await AdminHandlers._display_admin_main_menu(message, state)

    @admin_router.callback_query(F.data.startswith("admin_confirm_delete_order_"))
    async def admin_confirm_delete_order_callback(callback: CallbackQuery, state: FSMContext):
        """
        Запрашивает подтверждение удаления заказа.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

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

    @admin_router.callback_query(F.data.startswith("admin_delete_order_"))
    async def admin_delete_order_callback(callback: CallbackQuery, state: FSMContext):
        """
        Выполняет удаление заказа после подтверждения.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        order_id = int(callback.data.split("_")[3])
        logger.info(f"Админ {callback.from_user.id} подтвердил удаление заказа ID {order_id}.")

        deleted = await delete_order(order_id=order_id)

        await state.clear()

        if deleted:
            await callback.message.edit_text(f"Заказ №{order_id} успешно удален.", parse_mode="HTML")

            data = await state.get_data()
            current_page = data.get("current_page", 1)
            search_query = data.get("search_query")

            await AdminHandlers._display_orders_paginated(callback, state, current_page=current_page,
                                                          is_search=bool(search_query))
        else:
            await callback.answer("Не удалось удалить заказ. Заказ не найден.", show_alert=True)

            data = await state.get_data()
            original_message_id = data.get("original_message_id_for_delete_confirm")
            original_chat_id = data.get("original_chat_id_for_delete_confirm")
            original_chat_instance = data.get("original_chat_instance_for_delete_confirm")  # <-- Получаем chat_instance

            if original_message_id and original_chat_id and original_chat_instance:  # <-- Добавлена проверка
                mock_callback_query_message = Message(
                    chat=Chat(id=original_chat_id, type="private"),
                    message_id=original_message_id,
                    date=datetime.now(),
                    from_user=callback.from_user,
                    text="",
                    bot=callback.bot
                )
                mock_callback_query = CallbackQuery(
                    id=f"delete_return_fail_{order_id}_{datetime.now().timestamp()}",
                    from_user=callback.from_user,
                    message=mock_callback_query_message,
                    data=f"view_order_{order_id}",
                    chat_instance=original_chat_instance  # <-- Используем реальный chat_instance
                )
                await AdminHandlers.admin_view_order_details_callback(mock_callback_query, state)
            else:
                await callback.message.edit_text("Не удалось удалить заказ. Возвращаюсь в главное меню.",
                                                 parse_mode="HTML")
                await AdminHandlers._display_admin_main_menu(callback, state)

        await callback.answer()

    # --- ПОИСК ЗАКАЗОВ ---
    @admin_router.callback_query(F.data == "admin_find_orders")
    async def admin_find_orders_callback(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает нажатие кнопки "Найти заказы 🔍".
        Запрашивает у пользователя поисковый запрос и переводит в состояние ожидания ввода.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        logger.info(f"Админ {callback.from_user.id} начал поиск заказов. Текущее состояние: {await state.get_state()}")

        await callback.answer()

        await state.set_state(AdminStates.waiting_for_search_query)
        logger.info(f"Состояние админа {callback.from_user.id} установлено в {await state.get_state()}")

        await callback.message.edit_text(
            "Пожалуйста, введите ID заказа, часть имени пользователя или часть текста заказа для поиска:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Отмена", callback_data="admin_panel_back")]
            ]),
            parse_mode="HTML"
        )

    @admin_router.message(StateFilter(AdminStates.waiting_for_search_query))
    async def admin_process_search_query(message: Message, state: FSMContext):
        """
        Обрабатывает текстовое сообщение с поисковым запросом.
        Выполняет поиск и отображает результаты.
        """
        if message.from_user.id not in ADMIN_IDS:
            await message.answer("У вас нет прав для выполнения этой операции.")
            return

        search_query = message.text.strip()
        logger.info(f"Админ {message.from_user.id} ввел поисковый запрос: '{search_query}'.")

        await state.update_data(search_query=search_query)  # Сохраняем поисковый запрос в FSM-контексте
        await state.clear()  # Очищаем состояние после получения запроса, чтобы вернуться к нейтральному

        # Переходим к отображению первой страницы результатов поиска.
        await AdminHandlers._display_orders_paginated(message, state, current_page=1, is_search=True)

    @admin_router.callback_query(F.data.startswith("admin_search_page:"))
    async def admin_view_search_results_paginated_callback(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает пагинацию результатов поиска.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.", show_alert=True)
            return

        parts = callback.data.split(':')
        if len(parts) < 3:  # Ожидаем минимум 3 части: "admin_search_page", page_num, encoded_query
            logger.error(f"Неверный формат callback_data для пагинации поиска: {callback.data}")
            await callback.answer("Ошибка при обработке страницы.", show_alert=True)
            return

        try:
            current_page = int(parts[1])
            encoded_query = parts[2]
            search_query = urllib.parse.unquote_plus(encoded_query)
        except (ValueError, IndexError):
            logger.error(f"Неверный формат callback_data для пагинации поиска: {callback.data}")
            await callback.answer("Ошибка при обработке страницы.", show_alert=True)
            return

        logger.info(
            f"Админ {callback.from_user.id} переключает страницу поиска на {current_page} с запросом '{search_query}'.")
        await state.update_data(search_query=search_query)  # Убедимся, что search_query снова в FSM
        await AdminHandlers._display_orders_paginated(callback, state, current_page=current_page, is_search=True)

    # --- РАБОТА С СООБЩЕНИЯМИ ПОМОЩИ (HelpMessage) ---
    @admin_router.callback_query(F.data == "admin_manage_help_messages")
    async def admin_manage_help_messages_callback(callback: CallbackQuery):
        """
        Показывает меню управления сообщениями помощи.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        logger.info(f"Админ {callback.from_user.id} вошел в управление сообщениями помощи.")

        keyboard = InlineKeyboardBuilder()
        # Добавьте кнопки для создания, редактирования, просмотра, активации/деактивации сообщений помощи
        keyboard.row(
            InlineKeyboardButton(text="Просмотреть текущее сообщение помощи", callback_data="admin_view_help_message"))
        keyboard.row(InlineKeyboardButton(text="Создать/Редактировать сообщение помощи",
                                          callback_data="admin_edit_help_message"))
        # Добавьте другие кнопки, если нужны (например, история версий, удаление)
        keyboard.row(InlineKeyboardButton(text="🔙 В админ-панель", callback_data="admin_panel_back"))
        keyboard.adjust(1)

        await callback.message.edit_text(
            hbold("Меню управления сообщениями помощи:"),
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()

    @admin_router.callback_query(F.data == "admin_view_help_message")
    async def admin_view_help_message_callback(callback: CallbackQuery):
        """
        Отображает текущее активное сообщение помощи.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        active_message = await get_active_help_message_from_db()

        if active_message:
            text_to_display = (
                f"{hbold('Текущее активное сообщение помощи:')}\n\n"
                f"{active_message.text}\n\n"
                f"{hbold('Статус:')} {'Активно ✅' if active_message.is_active else 'Неактивно ❌'}\n"
                f"{hbold('Дата создания:')} {active_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}"
            )
        else:
            text_to_display = hbold("Активное сообщение помощи не найдено.")

        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))

        await callback.message.edit_text(
            text_to_display,
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()

    # Здесь могут быть другие хендлеры для создания/редактирования/активации сообщений помощи
    # Например:
    # @admin_router.callback_query(F.data == "admin_edit_help_message")
    # async def admin_edit_help_message_entry(callback: CallbackQuery, state: FSMContext):
    #     await state.set_state(AdminStates.waiting_for_help_message_text)
    #     await callback.message.edit_text("Введите новый текст для сообщения помощи:")
    #     await callback.answer()
    #
    # @admin_router.message(StateFilter(AdminStates.waiting_for_help_message_text))
    # async def admin_process_help_message_text(message: Message, state: FSMContext):
    #     new_help_text = message.text
    #     await update_or_create_help_message(new_help_text) # Нужно реализовать в db.py
    #     await message.answer("Сообщение помощи обновлено!")
    #     await state.clear()
    #     await AdminHandlers._display_admin_main_menu(message, state) # Вернуться в меню