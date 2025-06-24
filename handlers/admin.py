# handlers/admin.py
import logging
from aiogram import types, Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
import openpyxl
from io import BytesIO

from aiogram.filters import Command
from config import ADMIN_IDS
# Импортируем новую функцию delete_order
from database import get_all_orders, get_order_by_id, update_order_status, update_order_text, search_orders, \
    delete_order

admin_router = Router()


# Добавляем FSM для управления состоянием админской панели, в частности для пагинации
class AdminPanelState(StatesGroup):
    viewing_orders = State()  # Состояние, когда админ просматривает список заказов


class AdminOrderEditState(StatesGroup):
    waiting_for_new_text = State()


# Список статусов с эмодзи (перенесён сюда для удобства)
all_statuses_with_emojis = {
    "Новый": "🆕 Новый",
    "Обрабатывается": "⚙️ Обрабатывается",
    "Ожидает оплаты": "💰 Ожидает оплаты",
    "Отменен": "❌ Отменен",
    "Отправлен": "➡️ Отправлен",
    "В пути": "🚚 В пути",
    "Готов к выдаче": "✅ Готов к выдаче",
    "Получен": "👍 Получен",
    "Проблема с доставкой": "⚠️ Проблема с доставкой"
}

ORDERS_PER_PAGE = 10  # Количество заказов на одной странице пагинации


# --- Вспомогательные функции ---

def format_orders_list(orders):
    if not orders:
        return "Пока нет активных заказов."
    response = "<b>Список заказов:</b>\n\n"
    for order in orders:
        order_id, user_id, username, order_text, created_at, sent_at, received_at, status, *delivery_info = order  # Теперь извлекаем все поля
        truncated_text = (order_text[:50] + '...') if len(order_text) > 50 else order_text
        response += (f"📦 Заказ №{order_id}\n"
                     f"   От: {username}\n"
                     f"   Текст: {truncated_text}\n"
                     f"   Статус: <b>{status}</b>\n\n")
    return response


# НОВАЯ: Функция для генерации клавиатуры с пагинацией и кнопками действий
async def get_paginated_orders_markup(orders, current_page):
    start_index = current_page * ORDERS_PER_PAGE
    end_index = start_index + ORDERS_PER_PAGE
    page_orders = orders[start_index:end_index]

    inline_keyboard = []

    if not page_orders and current_page == 0:
        inline_keyboard.append(
            [types.InlineKeyboardButton(text="Нет заказов для отображения", callback_data="no_orders")])
    elif not page_orders and current_page > 0:
        inline_keyboard.append([types.InlineKeyboardButton(text="Конец списка", callback_data="end_of_list")])
    else:
        for order in page_orders:
            order_id, user_id, username, order_text, *rest = order
            truncated_text = (order_text[:30] + '...') if len(order_text) > 30 else order_text
            # Кнопка с информацией о заказе
            inline_keyboard.append([types.InlineKeyboardButton(
                text=f"📦 Заказ №{order_id} | {username} | {truncated_text}",
                callback_data=f"admin_view_order_{order_id}"
            )])
            # Кнопки действий под каждым заказом
            inline_keyboard.append([
                types.InlineKeyboardButton(text="📝 Изменить статус", callback_data=f"admin_change_status_{order_id}"),
                types.InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"admin_edit_text_{order_id}"),
                # Указываем order_id явно
                types.InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin_delete_order_confirm_{order_id}")
            ])

    # Кнопки пагинации
    pagination_buttons = []
    if current_page > 0:
        pagination_buttons.append(
            types.InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"admin_page_{current_page - 1}"))
    if end_index < len(orders):
        pagination_buttons.append(
            types.InlineKeyboardButton(text="Следующая ➡️", callback_data=f"admin_page_{current_page + 1}"))

    if pagination_buttons:
        inline_keyboard.append(pagination_buttons)

    # Дополнительные кнопки внизу
    inline_keyboard.append([types.InlineKeyboardButton(text="📊 Экспорт в Excel", callback_data="admin_export_excel")])

    return types.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


# --- Обработчики колбэков ---

# Обработчик просмотра деталей заказа
@admin_router.callback_query(F.data.startswith("admin_view_order_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_view_order_callback(callback_query: types.CallbackQuery):
    print(f"Callback 'admin_view_order_' получен от админа ID: {callback_query.from_user.id}")
    order_id = int(callback_query.data.split('_')[3])
    # Передаем callback_query.bot
    await send_order_details_to_admin(callback_query.bot, callback_query.message.chat.id, order_id, callback_query.id)


# НОВЫЙ: Обработчик для изменения статуса
@admin_router.callback_query(F.data.startswith("admin_change_status_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_prompt_change_status(callback_query: types.CallbackQuery, state: FSMContext):
    order_id = int(callback_query.data.split('_')[3])
    # Сохраняем order_id в FSM для следующего шага
    await state.update_data(current_order_id_for_status=order_id)

    # Создаем кнопки для выбора нового статуса
    status_buttons = []
    for status_key, status_label_with_emoji in all_statuses_with_emojis.items():
        status_buttons.append(
            types.InlineKeyboardButton(
                text=status_label_with_emoji,
                callback_data=f"admin_set_status_{status_key}_{order_id}"  # Теперь колбэк data включает order_id
            )
        )
    keyboard_rows = [status_buttons[i:i + 2] for i in range(0, len(status_buttons), 2)]
    keyboard_rows.append(
        [types.InlineKeyboardButton(text="⬅️ Отмена", callback_data="admin_back_to_current_page")])  # Кнопка отмены

    markup = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    await callback_query.message.edit_text(f"Выберите новый статус для заказа №{order_id}:", reply_markup=markup)
    await callback_query.answer()


# ОБНОВЛЕННЫЙ: Обработчик установки нового статуса
@admin_router.callback_query(F.data.startswith("admin_set_status_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_set_status_callback(callback_query: types.CallbackQuery, state: FSMContext):
    parts = callback_query.data.split('_')
    new_status = parts[3]  # С 3, т.к. "admin_set_status_<status_key>_<order_id>"
    order_id = int(parts[4])

    # Обновляем статус
    update_order_status(order_id, new_status)
    await callback_query.answer(
        f"Статус заказа №{order_id} изменен на '{all_statuses_with_emojis.get(new_status, new_status)}'",
        show_alert=False)

    # --- Уведомление пользователя о смене статуса на "Обрабатывается" ---
    if new_status == "Обрабатывается":
        order = get_order_by_id(order_id)
        if order:
            user_id = order[1]  # user_id находится во втором поле (индекс 1)
            try:
                # Используем callback_query.bot для отправки сообщения
                await callback_query.bot.send_message(user_id,
                                                      f"✅ Ваш заказ №{order_id} сейчас в обработке! Мы скоро свяжемся с вами.")
                logging.info(
                    f"Уведомление отправлено пользователю {user_id} о статусе 'Обрабатывается' для заказа {order_id}")
            except Exception as e:
                logging.error(f"Не удалось отправить уведомление пользователю {user_id} для заказа {order_id}: {e}")
    # -------------------------------------------------------------------

    # Возвращаемся к списку заказов на текущей странице
    user_data = await state.get_data()
    current_page = user_data.get('current_page', 0)
    await show_paginated_orders(callback_query.message, state, current_page, edit_message=True)  # Обновляем список


# НОВЫЙ: Обработчик для кнопки "Редактировать"
@admin_router.callback_query(F.data.startswith("admin_edit_text_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_edit_text_callback(callback_query: types.CallbackQuery, state: FSMContext):
    order_id = int(callback_query.data.split('_')[3])  # Извлекаем order_id
    await state.update_data(order_id=order_id)
    await callback_query.message.edit_text("Пожалуйста, отправь новый текст для заказа.")
    await state.set_state(AdminOrderEditState.waiting_for_new_text)
    await callback_query.answer()


# НОВЫЙ: Обработчик для подтверждения удаления
@admin_router.callback_query(F.data.startswith("admin_delete_order_confirm_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_delete_order_confirm(callback_query: types.CallbackQuery):
    order_id = int(callback_query.data.split('_')[4])  # order_id находится в 5-й части
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Да, удалить", callback_data=f"admin_delete_order_execute_{order_id}")],
        [types.InlineKeyboardButton(text="Нет, отмена", callback_data="admin_back_to_current_page")]
    ])
    await callback_query.message.edit_text(f"Ты уверен, что хочешь удалить заказ №{order_id}? Это действие необратимо.",
                                           reply_markup=markup)
    await callback_query.answer()


# НОВЫЙ: Обработчик для выполнения удаления
@admin_router.callback_query(F.data.startswith("admin_delete_order_execute_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_delete_order_execute(callback_query: types.CallbackQuery, state: FSMContext):
    order_id = int(callback_query.data.split('_')[4])  # order_id находится в 5-й части

    delete_order(order_id)  # Вызываем новую функцию удаления
    await callback_query.answer(f"Заказ №{order_id} удален.", show_alert=True)

    # Возвращаемся к списку заказов на текущей странице
    user_data = await state.get_data()
    current_page = user_data.get('current_page', 0)
    await show_paginated_orders(callback_query.message, state, current_page, edit_message=True)  # Обновляем список


@admin_router.message(AdminOrderEditState.waiting_for_new_text, F.from_user.id.in_(ADMIN_IDS))
async def process_new_order_text(message: types.Message, state: FSMContext):
    print(f"Новый текст заказа получен от админа ID: {message.from_user.id}")
    data = await state.get_data()
    order_id = data.get('order_id')
    new_text = message.text

    if order_id:
        update_order_text(order_id, new_text)
        await message.reply(f"Текст заказа №{order_id} успешно обновлен.")

        await send_order_details_to_admin(message.bot, message.chat.id, order_id)
    else:
        await message.reply("Произошла ошибка. Не удалось найти ID заказа для обновления.")

    await state.clear()
    # После редактирования текста, можно перенаправить админа обратно к списку заказов
    await show_paginated_orders(message, state, current_page=0)  # Или на ту страницу, с которой пришли


@admin_router.callback_query(F.data == "admin_export_excel", F.from_user.id.in_(ADMIN_IDS))
async def admin_export_excel_callback(callback_query: types.CallbackQuery):
    print(f"Callback 'admin_export_excel' получен от админа ID: {callback_query.from_user.id}")
    orders = get_all_orders()
    if not orders:
        await callback_query.answer("Нет заказов для экспорта.", show_alert=True)
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Заказы"

    # Заголовки (теперь с новыми полями)
    headers = ["ID Заказа", "ID Пользователя", "Имя Пользователя", "Текст Заказа", "Дата Создания",
               "Дата Отправки", "Дата Получения", "Статус",
               "ФИО", "Адрес Доставки", "Метод Оплаты", "Телефон", "Примечания"]
    ws.append(headers)

    # Данные (обновлено для извлечения всех полей)
    for order in orders:
        formatted_order = list(order)
        # Преобразование дат в читаемый формат, если они не None
        # Проверяем, что индексы существуют перед доступом
        date_indices = [4, 5, 6]  # created_at, sent_at, received_at
        for idx in date_indices:
            if len(formatted_order) > idx and formatted_order[idx]:
                try:
                    formatted_order[idx] = datetime.fromisoformat(formatted_order[idx]).strftime('%Y-%m-%d %H:%M')
                except ValueError:
                    formatted_order[idx] = "Некорректная дата"  # Обработка ошибки, если формат даты неправильный
        ws.append(formatted_order)

    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    await callback_query.message.answer_document(
        types.BufferedInputFile(excel_file.getvalue(), filename="orders.xlsx"),
        caption="Вот твои заказы в формате Excel."
    )
    await callback_query.answer("Файл Excel отправлен.")


# НОВЫЙ: Обработчик для пагинации
@admin_router.callback_query(F.data.startswith("admin_page_"), F.from_user.id.in_(ADMIN_IDS))
async def admin_paginate_orders(callback_query: types.CallbackQuery, state: FSMContext):
    current_page = int(callback_query.data.split('_')[2])
    await show_paginated_orders(callback_query.message, state, current_page, edit_message=True)
    await callback_query.answer()


# ОБНОВЛЕННЫЙ: Обработчик "Назад к списку"
@admin_router.callback_query(F.data == "admin_back_to_list", F.from_user.id.in_(ADMIN_IDS))
async def admin_back_to_list_callback(callback_query: types.CallbackQuery, state: FSMContext):
    # Возвращаемся на ту страницу, с которой пришли, или на первую
    user_data = await state.get_data()
    current_page = user_data.get('current_page', 0)
    await show_paginated_orders(callback_query.message, state, current_page, edit_message=True)
    await callback_query.answer()


# --- Обработчики команд администратора ---

@admin_router.message(Command(commands=["admin"]), F.from_user.id.in_(ADMIN_IDS))
async def cmd_admin(message: types.Message, state: FSMContext):
    """
    Основная команда для администраторов.
    Выводит первую страницу списка заказов с пагинацией.
    """
    print(f"!!! cmd_admin: Команда /admin получена от ID: {message.from_user.id}")
    print(f"!!! cmd_admin: ADMIN_IDS из config.py: {ADMIN_IDS}")
    print(f"!!! cmd_admin: Проверяем: {message.from_user.id} in ADMIN_IDS -> {message.from_user.id in ADMIN_IDS}")

    # Устанавливаем текущее состояние на просмотр заказов
    await state.set_state(AdminPanelState.viewing_orders)
    # Показываем первую страницу заказов
    await show_paginated_orders(message, state, current_page=0)


@admin_router.message(Command(commands=["admin_search"]), F.from_user.id.in_(ADMIN_IDS))
async def cmd_admin_search(message: types.Message):
    print(f"!!! cmd_admin_search: Команда /admin_search получена от ID: {message.from_user.id}")
    print(f"!!! cmd_admin_search: ADMIN_IDS из config.py: {ADMIN_IDS}")
    print(
        f"!!! cmd_admin_search: Проверяем: {message.from_user.id} in ADMIN_IDS -> {message.from_user.id in ADMIN_IDS}")

    query_parts = message.text.split('/admin_search ', 1)
    if len(query_parts) < 2:
        await message.reply("Используйте: /admin_search <ID заказа или ключевые слова>")
        return

    search_query = query_parts[1].strip()
    orders = search_orders(search_query)

    response = f"<b>Результаты поиска по '{search_query}':</b>\n\n" + format_orders_list(orders)

    # Для поиска не нужна пагинация, если результат небольшой.
    # Если результатов много, можно добавить пагинацию и сюда.
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔍 Посмотреть все", callback_data="admin_view_all_orders")]
        # Возвращает к общему списку с пагинацией
    ])
    await message.reply(response, reply_markup=markup, parse_mode='HTML')


# НОВАЯ: Основная функция для отображения списка заказов с пагинацией
async def show_paginated_orders(message: types.Message, state: FSMContext, current_page: int,
                                edit_message: bool = False):
    orders = get_all_orders()  # Получаем все заказы
    await state.update_data(current_page=current_page)  # Сохраняем текущую страницу в FSM

    start_index = current_page * ORDERS_PER_PAGE
    end_index = start_index + ORDERS_PER_PAGE
    page_orders = orders[start_index:end_index]

    if not page_orders:
        if current_page > 0:
            response_text = "Вы достигли конца списка заказов."
        else:
            response_text = "На данный момент активных заказов нет."
    else:
        response_text = f"<b>Список заказов (страница {current_page + 1}/{((len(orders) - 1) // ORDERS_PER_PAGE) + 1 if len(orders) > 0 else 1}):</b>\n\n"
        for order in page_orders:
            order_id, _, username, order_text, created_at, *rest = order
            truncated_text = (order_text[:40] + '...') if len(order_text) > 40 else order_text
            response_text += f"📦 Заказ №{order_id} от {username}: {truncated_text}\n"

    markup = await get_paginated_orders_markup(orders, current_page)

    if edit_message and message.from_user.id in ADMIN_IDS:  # Убедимся, что это админ, который нажимает кнопки
        try:
            await message.edit_text(response_text, reply_markup=markup, parse_mode='HTML')
        except Exception as e:
            logging.error(f"Ошибка при редактировании сообщения пагинации: {e}")
            # Если не удалось отредактировать (например, сообщение слишком старое), отправляем новое
            await message.answer(response_text, reply_markup=markup, parse_mode='HTML')
    else:
        await message.answer(response_text, reply_markup=markup, parse_mode='HTML')


# --- Вспомогательная функция для отправки деталей заказа ---
async def send_order_details_to_admin(bot: Bot, chat_id: int, order_id: int, callback_query_id: str = None):
    # Теперь 'bot' явно передаётся
    # Перемещаем _last_message_id_for_edit в объект bot, если он там не хранится глобально
    if not hasattr(bot, '_last_message_id_for_edit'):
        bot._last_message_id_for_edit = {}

    order = get_order_by_id(order_id)
    if not order:
        if callback_query_id:
            await bot.answer_callback_query(callback_query_id, "Заказ не найден.")
        await bot.send_message(chat_id, "Заказ не найден.")
        return

    order_id, user_id, username, order_text, created_at_iso, sent_at_iso, received_at_iso, status, \
        full_name, delivery_address, payment_method, contact_phone, delivery_notes = order

    created_at_dt = datetime.fromisoformat(created_at_iso)
    formatted_created_at = created_at_dt.strftime('%d.%m.%Y %H:%M')

    formatted_sent_at = datetime.fromisoformat(sent_at_iso).strftime('%d.%m.%Y %H:%M') if sent_at_iso else "N/A"
    formatted_received_at = datetime.fromisoformat(received_at_iso).strftime(
        '%d.%m.%Y %H:%M') if received_at_iso else "N/A"

    admin_message = (f"📝 <b>Детали заказа №{order_id}</b>\n\n"
                     f"👤 От: {username} (ID: <code>{user_id}</code>)\n"
                     f"📝 Текст заказа: {order_text}\n"
                     f"⏰ Создан: {formatted_created_at}\n"
                     f"➡️ Отправлен: {formatted_sent_at}\n"
                     f"✅ Получен: {formatted_received_at}\n"
                     f"📍 Статус: <b>{status}</b>\n\n"
                     f"--- Детали доставки ---\n"
                     f"ФИО: {full_name or 'Не указано'}\n"
                     f"Адрес: {delivery_address or 'Не указано'}\n"
                     f"Оплата: {payment_method or 'Не указано'}\n"
                     f"Телефон: {contact_phone or 'Не указано'}\n"
                     f"Примечания: {delivery_notes or 'Нет'}")

    # Создаем кнопки для изменения статуса
    status_buttons_list = []
    for status_key, status_label_with_emoji in all_statuses_with_emojis.items():
        status_buttons_list.append(
            types.InlineKeyboardButton(
                text=status_label_with_emoji,
                callback_data=f"admin_set_status_{status_key}_{order_id}"
            )
        )
    # Разделяем кнопки на ряды по 2
    keyboard_rows = [status_buttons_list[i:i + 2] for i in range(0, len(status_buttons_list), 2)]

    # Добавляем кнопки редактирования и удаления
    keyboard_rows.append([
        types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data=f"admin_edit_text_{order_id}"),
        types.InlineKeyboardButton(text="🗑️ Удалить заказ", callback_data=f"admin_delete_order_confirm_{order_id}")
    ])
    keyboard_rows.append([types.InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_back_to_list")])

    markup = types.InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    try:
        if callback_query_id:
            await bot.edit_message_text(  # Используем переданный 'bot'
                chat_id=chat_id,
                message_id=bot._last_message_id_for_edit.get(chat_id),  # Используем переданный 'bot'
                text=admin_message,
                reply_markup=markup,
                parse_mode='HTML'
            )
            await bot.answer_callback_query(callback_query_id)
        else:
            sent_message = await bot.send_message(  # Используем переданный 'bot'
                chat_id,
                admin_message,
                reply_markup=markup,
                parse_mode='HTML'
            )
            bot._last_message_id_for_edit[chat_id] = sent_message.message_id  # Используем переданный 'bot'
    except Exception as e:
        logging.error(f"Ошибка при отправке/редактировании деталей заказа: {e}")
        await bot.send_message(chat_id, "Произошла ошибка при отображении деталей заказа.")
