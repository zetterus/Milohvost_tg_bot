# handlers/admin_handlers.py
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, StateFilter
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.markdown import hbold, hcode, hlink, hitalic
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# Константы ORDERS_PER_PAGE и MAX_PREVIEW_TEXT_LENGTH теперь импортируются из config
from config import ADMIN_IDS, ORDER_STATUS_MAP, ORDERS_PER_PAGE, MAX_PREVIEW_TEXT_LENGTH
from db import get_all_orders, get_order_by_id, update_order_status, search_orders
from models import Order, HelpMessage


# Пример, если states.py еще нет:
class AdminStates(StatesGroup):
    waiting_for_search_query = State()


logger = logging.getLogger(__name__)

admin_router = Router()


class AdminHandlers:
    """
    Класс для обработки команд и взаимодействий администраторов.
    Используем HTML-форматирование.
    """

    # --- АДМИНСКОЕ МЕНЮ ---
    @staticmethod
    async def _display_admin_main_menu(update_object: Message | CallbackQuery):
        """
        Отображает главное меню админ-панели.
        Принимает Message или CallbackQuery и соответствующим образом отправляет/редактирует сообщение.
        """
        user_id = update_object.from_user.id

        if user_id not in ADMIN_IDS:
            if isinstance(update_object, Message):
                await update_object.answer("У вас нет прав для доступа к админ-панели.")
            elif isinstance(update_object, CallbackQuery):
                await update_object.answer("У вас нет прав для доступа к админ-панели.", show_alert=True)
            return

        logger.info(f"Админ {user_id} вошел/вернулся в админ-панель.")

        # Создаем клавиатуру админ-панели
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Просмотреть все заказы 📋", callback_data="admin_orders_page_1")
        keyboard.button(text="Найти заказы 🔍", callback_data="admin_find_orders")
        keyboard.button(text="Управление помощью 💬", callback_data="admin_manage_help_messages")
        keyboard.adjust(1)  # Кнопки в один столбец

        text = hbold("Добро пожаловать в админ-панель! Выберите действие:")
        reply_markup = keyboard.as_markup()

        # Определяем, как ответить: отправить новое сообщение или редактировать существующее
        if isinstance(update_object, Message):
            await update_object.answer(
                text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
        elif isinstance(update_object, CallbackQuery):
            await update_object.answer()  # Отвечаем на коллбэк, чтобы убрать "часики"
            await update_object.message.edit_text(  # Редактируем сообщение
                text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )

    @admin_router.message(Command("admin"))
    async def admin_command(message: Message):
        """
        Обрабатывает команду /admin.
        Проверяет админ-права и отображает главное меню админ-панели.
        """
        await AdminHandlers._display_admin_main_menu(message)

    @admin_router.callback_query(F.data == "admin_panel_back")
    async def admin_panel_callbacks(callback: CallbackQuery):
        """
        Обрабатывает коллбэки для возврата в админ-панель из подменю ("admin_panel_back").
        """
        await AdminHandlers._display_admin_main_menu(callback)

    # --- ОТОБРАЖЕНИ СТРАНИЦЫ СО ВСЕМ ЗАКАЗАМИ/РЕЗУЛЬТАТАМИ ПОИСКА ---
    @staticmethod
    async def _get_paginated_orders_menu(
            orders: list[Order],
            current_page: int,
            total_orders: int,
            message_context: str = "всех заказов",  # "всех заказов" или "поиска"
            query: str = None  # Для будущих функций поиска
    ):
        """
        Генерирует меню пагинации для списка заказов.

        :param orders: Список объектов Order, отфильтрованных для текущей страницы.
        :param current_page: Текущий номер страницы (начиная с 1).
        :param total_orders: Общее количество заказов.
        :param message_context: Контекст сообщения (например, "всех заказов", "поиска").
        :param query: Поисковый запрос, если есть.
        :return: Кортеж (текст сообщения, InlineKeyboardBuilder)
        """
        total_pages = (total_orders + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE

        # --- Текст сообщения ---
        if query:
            header_text = hbold(f"Результаты поиска по запросу '{query}' (Страница {current_page}/{total_pages}):")
        else:
            header_text = hbold(f"Список {message_context} (Страница {current_page}/{total_pages}):")

        orders_text = header_text + "\n\n"

        if not orders:
            orders_text += "Заказов на этой странице нет."

        # --- Кнопки заказов ---
        order_buttons_builder = InlineKeyboardBuilder()
        for order in orders:
            display_status = ORDER_STATUS_MAP.get(order.status, order.status)

            # Превью текста заказа, обрезанное и экранированное
            preview_text = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
            if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
                preview_text += "..."

            button_text = f"#{order.id} | {preview_text} | {display_status}"
            order_buttons_builder.add(InlineKeyboardButton(
                text=button_text,
                callback_data=f"view_order_{order.id}"  # Этот callback_data остался прежним
            ))
        order_buttons_builder.adjust(1)  # Кнопки заказов по одной в ряд

        # --- Кнопки пагинации ---
        pagination_builder = InlineKeyboardBuilder()

        # Кнопки "На первую" и "На 5 назад"
        if current_page > 1:
            pagination_builder.button(text="⏮️", callback_data=f"admin_orders_page_{1}")
        if current_page > 5:  # Показываем только если можно перейти на 5 страниц назад
            pagination_builder.button(text="◀️5", callback_data=f"admin_orders_page_{max(1, current_page - 5)}")
        if current_page > 1:
            pagination_builder.button(text="◀️", callback_data=f"admin_orders_page_{current_page - 1}")

        # Кнопки "На 1 вперед", "На 5 вперед", "На последнюю"
        if current_page < total_pages:
            pagination_builder.button(text="▶️", callback_data=f"admin_orders_page_{current_page + 1}")
        if current_page < total_pages - 4:  # Показываем только если есть еще 5 страниц впереди
            pagination_builder.button(text="▶️5",
                                      callback_data=f"admin_orders_page_{min(total_pages, current_page + 5)}")
        if current_page < total_pages:
            pagination_builder.button(text="⏭️", callback_data=f"admin_orders_page_{total_pages}")

        # Комбинируем клавиатуры
        final_keyboard = InlineKeyboardBuilder()
        final_keyboard.attach(order_buttons_builder)  # Сначала кнопки заказов

        if total_orders > ORDERS_PER_PAGE:  # Показываем пагинацию только если есть больше одной страницы
            final_keyboard.attach(pagination_builder)  # Затем кнопки пагинации

        # Кнопка "Назад в админ-панель" внизу
        final_keyboard.row(InlineKeyboardButton(
            text="🔙 В админ-панель",
            callback_data="admin_panel_back"
        ))

        return orders_text, final_keyboard.as_markup()  # Возвращаем готовый markup

    @admin_router.callback_query(F.data.startswith("admin_orders_page_"))
    async def admin_view_all_orders_paginated_callback(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает нажатие инлайн-кнопок пагинации (как для просмотра всех заказов, так и для результатов поиска).
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        # Извлекаем номер страницы
        try:
            current_page = int(callback.data.split("_")[-1])  # Последний элемент после _
        except (ValueError, IndexError):
            logger.error(f"Неверный формат callback_data для пагинации: {callback.data}")
            await callback.answer("Ошибка при обработке страницы.", show_alert=True)
            return

        logger.info(f"Админ {callback.from_user.id} просматривает заказы на странице {current_page}.")

        # Получаем данные из состояния FSM. Если состояния нет, значит, это просмотр всех заказов
        data = await state.get_data()
        search_query = data.get("search_query")  # Получаем поисковый запрос, если есть

        if search_query:
            # Если есть поисковый запрос, ищем заказы по нему
            found_orders = await search_orders(search_query)
            total_orders = len(found_orders)
            start_index = (current_page - 1) * ORDERS_PER_PAGE
            end_index = start_index + ORDERS_PER_PAGE
            orders_on_page = found_orders[start_index:end_index]

            orders_text, keyboard_markup = await AdminHandlers._get_paginated_orders_menu(
                orders=orders_on_page,
                current_page=current_page,
                total_orders=total_orders,
                message_context="результатов поиска",  # Контекст для заголовка
                query=search_query  # Передаем поисковый запрос
            )
        else:
            # Если нет поискового запроса, показываем все заказы
            all_orders = await get_all_orders()  # Получаем все заказы
            total_orders = len(all_orders)

            # Вычисляем индексы для выборки заказов на текущей странице
            start_index = (current_page - 1) * ORDERS_PER_PAGE
            end_index = start_index + ORDERS_PER_PAGE
            orders_on_page = all_orders[start_index:end_index]

            # Генерируем меню пагинации
            orders_text, keyboard_markup = await AdminHandlers._get_paginated_orders_menu(
                orders=orders_on_page,
                current_page=current_page,
                total_orders=total_orders,
                message_context="всех заказов"  # Контекст для заголовка
            )

        await callback.message.edit_text(
            orders_text,
            reply_markup=keyboard_markup,  # Теперь это уже готовый markup
            parse_mode="HTML"
        )
        await callback.answer()

    @classmethod
    @admin_router.callback_query(F.data.startswith("view_order_"))
    async def admin_view_order_details_callback(callback: CallbackQuery):
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
                f"{hbold('Детали заказа №')}{hbold(str(order.id))}\n\n"
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
                        callback_data=f"admin_change_status_{order.id}_{status_key}"  # <-- ИСПРАВЛЕНО
                    ))
            status_keyboard.add(InlineKeyboardButton(
                text="⬅️ Назад к заказам",
                callback_data="admin_orders_page_1"  # <-- ИСПРАВЛЕНО
            ))
            status_keyboard.adjust(2)

            await callback.message.edit_text(
                order_details_text,
                reply_markup=status_keyboard.as_markup(),
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text("Заказ не найден.", parse_mode="HTML")

        await callback.answer()

    @admin_router.callback_query(F.data.startswith("admin_change_status_"))  # <-- ИСПРАВЛЕНО
    async def admin_change_order_status_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие кнопки для изменения статуса заказа.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        # Парсинг callback_data для admin_change_status_order_id_status_key
        parts = callback.data.split('_')  # Например: ['admin', 'change', 'status', '123', 'pending']
        if len(parts) < 5:  # Ожидаем минимум 5 частей
            await callback.answer("Неверный формат данных коллбэка для статуса.", show_alert=True)
            return

        try:
            order_id = int(parts[3])  # ID заказа
            new_status = parts[4]  # Новый статус
        except (ValueError, IndexError):
            await callback.answer("Неверный ID заказа или статус.", show_alert=True)
            return

        logger.info(f"Админ {callback.from_user.id} меняет статус заказа ID {order_id} на '{new_status}'.")

        updated_order = await update_order_status(order_id, new_status)

        if updated_order:
            display_status = ORDER_STATUS_MAP.get(updated_order.status, updated_order.status)
            await callback.answer(f"Статус заказа №{order_id} изменен на '{display_status}'!", show_alert=True)

            temp_callback_data = f"view_order_{order_id}"
            temp_callback_query = CallbackQuery(id=callback.id, from_user=callback.from_user, message=callback.message,
                                                data=temp_callback_data)
            await AdminHandlers.admin_view_order_details_callback(temp_callback_query)
        else:
            await callback.answer("Не удалось изменить статус заказа. Заказ не найден.", show_alert=True)
            await callback.message.edit_text("Ошибка: Заказ не найден.", parse_mode="HTML")

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

        await callback.answer()  # Убираем "часики"

        await state.set_state(AdminStates.waiting_for_search_query)  # Переходим в состояние ожидания ввода
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
            await state.clear()
            return

        logger.info(
            f"Админ {message.from_user.id} ввел поисковый запрос: '{message.text}'. Текущее состояние: {await state.get_state()}")

        search_query = message.text.strip()

        await state.clear()  # Сбрасываем состояние, поиск завершен
        logger.info(f"Состояние админа {message.from_user.id} сброшено.")  # Сбрасываем состояние, поиск завершен

        # Выполняем поиск в базе данных (предполагается, что у вас есть такая функция)
        found_orders = await search_orders(search_query)

        if found_orders:
            # Отображаем результаты поиска с пагинацией (используем вашу функцию)
            orders_text, keyboard_markup = await AdminHandlers._get_paginated_orders_menu(
                orders=found_orders,
                current_page=1,  # Начинаем с первой страницы
                total_orders=len(found_orders),
                message_context="результатов поиска",  # Меняем контекст сообщения
                query=search_query  # Передаем поисковый запрос для отображения
            )
            await message.answer(
                orders_text,
                reply_markup=keyboard_markup,
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"По запросу '{search_query}' ничего не найдено.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад в админ-панель", callback_data="admin_panel_back")]
                ]),
                parse_mode="HTML"
            )

    # --- РАБОТА С СООБЩЕНИЯМИ ПОМОЩИ ---
    @admin_router.callback_query(F.data == "admin_manage_help_messages")
    async def admin_manage_help_messages_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие инлайн-кнопки "Управление помощью".
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        logger.info(f"Админ {callback.from_user.id} нажал 'Управление помощью'.")
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Создать/Редактировать сообщение ✏️", callback_data="admin_create_edit_help")
        keyboard.button(text="Выбрать активное сообщение ✅", callback_data="admin_select_active_help")
        keyboard.button(text="Назад в админ-панель 🔙", callback_data="admin_panel_back")
        keyboard.adjust(1)

        await callback.message.edit_text(
            hbold("Управление сообщениями помощи:"),
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()
