from config import ADMIN_IDS

print("Admin router initialized")
# handlers/admin.py
import logging
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from datetime import datetime
import openpyxl
from io import BytesIO

from database import (
    get_all_orders, get_order_by_id, update_order_status,
    search_orders, update_order_text
)
from config import ADMIN_IDS
admin_router = Router()

class AdminOrderEditState(StatesGroup):
    waiting_for_new_text = State()

# --- Вспомогательные функции ---
def format_order_details(order_data: tuple) -> str:
    if not order_data:
        return "Заказ не найден."
    order_id, user_id, username, order_text, created_at, sent_at, received_at, status = order_data
    created_dt = datetime.fromisoformat(created_at).strftime('%d.%m.%Y %H:%M')
    sent_dt = datetime.fromisoformat(sent_at).strftime('%d.%m.%Y %H:%M') if sent_at else "Не отправлен"
    received_dt = datetime.fromisoformat(received_at).strftime('%d.%m.%Y %H:%M') if received_at else "Не получен"
    return (
        f"<b>Информация о заказе №{order_id}</b>\n\n"
        f"👤 Клиент: {username} (ID: <code>{user_id}</code>)\n"
        f"📝 Текст заказа:\n{order_text}\n\n"
        f"⏰ Создан: {created_dt}\n"
        f"➡️ Отправлен: {sent_dt}\n"
        f"✅ Получен: {received_dt}\n"
        f"📊 Статус: <b>{status}</b>"
    )

def get_admin_order_markup(order_id: int, current_status: str) -> types.InlineKeyboardMarkup:
    inline_keyboard = []
    all_statuses = ["Новый", "Обрабатывается", "Ожидает оплаты", "Отменен", "Отправлен", "В пути", "Готов к выдаче", "Получен", "Проблема с доставкой"]
    status_buttons_row = []
    for status in all_statuses:
        if status != current_status:
            status_buttons_row.append(
                types.InlineKeyboardButton(text=f"Статус: {status}", callback_data=f"admin_status_{status}_{order_id}")
            )
            if len(status_buttons_row) == 2:
                inline_keyboard.append(status_buttons_row)
                status_buttons_row = []
    if status_buttons_row:
        inline_keyboard.append(status_buttons_row)

    inline_keyboard.append([
        types.InlineKeyboardButton(text="✏️ Редактировать текст", callback_data=f"admin_edit_text_{order_id}"),
        types.InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="admin_back_to_list")
    ])
    return types.InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

def format_orders_list(orders: list) -> str:
    if not orders:
        return "На данный момент активных заказов нет."
    response = "<b>Список всех заказов:</b>\n\n"
    for order in orders:
        order_id, user_id, username, order_text, created_at, _, _, status = order
        truncated_text = (order_text[:40] + '...') if len(order_text) > 40 else order_text
        response += (f"📦 №{order_id} | {status} | Клиент: {username} | {truncated_text}\n"
                     f"  Создан: {datetime.fromisoformat(created_at).strftime('%d.%m.%Y %H:%M')}\n\n")
    return response

# --- Обработчики команд администратора ---



@admin_router.message(Command(commands=["admin"])) # Убрали фильтр F.user.id.in_(ADMIN_IDS) отсюда
async def cmd_admin(message: types.Message):
    """
    Основная команда для администраторов.
    Выводит список всех заказов по умолчанию.
    """
    # --- Ручная проверка ID администратора внутри функции ---
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав администратора для выполнения этой команды.")
        logging.warning(f"Попытка доступа к админ-команде от неадминистратора: {message.from_user.id}")
        return # Останавливаем выполнение функции, если пользователь не админ
    # --------------------------------------------------------

    print(f"Админская команда /admin получена от ID: {message.from_user.id}") # Оставляем для отладки
    orders = get_all_orders()
    response = format_orders_list(orders)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔍 Посмотреть все", callback_data="admin_view_all_orders")],
        [types.InlineKeyboardButton(text="📊 Экспорт в Excel", callback_data="admin_export_excel")]
    ])
    await message.reply(response, reply_markup=markup, parse_mode='HTML')


@admin_router.message(Command(commands=["admin_search"])) # То же самое и здесь
async def cmd_admin_search(message: types.Message):
    """
    Поиск заказов по ID или ключевым словам.
    Использование: /admin_search <запрос>
    """
    # --- Ручная проверка ID администратора внутри функции ---
    if message.from_user.id not in ADMIN_IDS:
        await message.reply("У вас нет прав администратора для выполнения этой команды.")
        logging.warning(f"Попытка доступа к админ-команде от неадминистратора: {message.from_user.id}")
        return # Останавливаем выполнение функции, если пользователь не админ
    # --------------------------------------------------------

    print(f"Админская команда /admin_search получена от ID: {message.from_user.id}") # Оставляем для отладки
    query_parts = message.text.split('/admin_search ', 1)
    if len(query_parts) < 2:
        await message.reply("Используйте: /admin_search <ID заказа или ключевые слова>")
        return

    search_query = query_parts[1].strip()
    orders = search_orders(search_query)

    response = f"<b>Результаты поиска по '{search_query}':</b>\n\n" + format_orders_list(orders)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔍 Посмотреть все", callback_data="admin_view_all_orders")]
    ])
    await message.reply(response, reply_markup=markup, parse_mode='HTML')

# --- Обработчики Callback Query (Inline-кнопок) (без изменений) ---

@admin_router.callback_query(F.data == "admin_view_all_orders", F.from_user.id.in_(ADMIN_IDS))
async def callback_view_all_orders(callback: types.CallbackQuery):
    orders = get_all_orders()
    response = format_orders_list(orders)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📊 Экспорт в Excel", callback_data="admin_export_excel")]
    ])
    await callback.message.edit_text(response, reply_markup=markup, parse_mode='HTML')
    await callback.answer()


@admin_router.callback_query(F.data.startswith("admin_view_order_") & F.from_user.id.in_(ADMIN_IDS))
async def callback_view_order_details(callback: types.CallbackQuery):
    order_id = int(callback.data.split('_')[-1])
    order_data = get_order_by_id(order_id)
    if not order_data:
        await callback.message.edit_text("Заказ не найден.")
        await callback.answer()
        return
    formatted_text = format_order_details(order_data)
    current_status = order_data[7]
    markup = get_admin_order_markup(order_id, current_status)
    await callback.message.edit_text(formatted_text, reply_markup=markup, parse_mode='HTML')
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin_status_") & F.from_user.id.in_(ADMIN_IDS))
async def callback_change_order_status(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    new_status = parts[2]
    order_id = int(parts[3])
    update_order_status(order_id, new_status)
    order_data = get_order_by_id(order_id)
    if order_data:
        formatted_text = format_order_details(order_data)
        current_status = order_data[7]
        markup = get_admin_order_markup(order_id, current_status)
        await callback.message.edit_text(formatted_text, reply_markup=markup, parse_mode='HTML')
        await callback.answer(f"Статус заказа №{order_id} изменен на '{new_status}'")
    else:
        await callback.message.edit_text("Заказ не найден после обновления статуса.")
        await callback.answer("Ошибка обновления статуса.")

@admin_router.callback_query(F.data.startswith("admin_edit_text_") & F.from_user.id.in_(ADMIN_IDS))
async def callback_edit_order_text(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split('_')[-1])
    order_data = get_order_by_id(order_id)
    if not order_data:
        await callback.message.edit_text("Заказ не найден.")
        await callback.answer()
        return
    await state.set_state(AdminOrderEditState.waiting_for_new_text)
    await state.update_data(order_id=order_id, original_message_id=callback.message.message_id, chat_id=callback.message.chat.id)
    await callback.message.edit_text(f"Введите новый текст для заказа №{order_id}:\n\nТекущий текст:\n`{order_data[3]}`",
                                     parse_mode='Markdown')
    await callback.answer()

@admin_router.message(AdminOrderEditState.waiting_for_new_text, F.user.id.in_(ADMIN_IDS))
async def process_new_order_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get('order_id')
    original_message_id = data.get('original_message_id')
    chat_id = data.get('chat_id')
    new_text = message.text
    update_order_text(order_id, new_text)
    order_data = get_order_by_id(order_id)
    await state.clear()
    if order_data:
        formatted_text = format_order_details(order_data)
        current_status = order_data[7]
        markup = get_admin_order_markup(order_id, current_status)
        try:
            await message.bot.edit_message_text(
                chat_id=chat_id,
                message_id=original_message_id,
                text=formatted_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            await message.answer(f"✅ Текст заказа №{order_id} успешно обновлен!")
        except Exception as e:
            logging.error(f"Не удалось отредактировать сообщение {original_message_id} в чате {chat_id}: {e}")
            await message.answer(formatted_text, reply_markup=markup, parse_mode='HTML')
            await message.answer(f"✅ Текст заказа №{order_id} успешно обновлен (новое сообщение).")
    else:
        await message.answer("Заказ не найден после обновления текста.")

@admin_router.callback_query(F.data == "admin_export_excel", F.from_user.id.in_(ADMIN_IDS))
async def callback_export_excel(callback: types.CallbackQuery):
    orders = get_all_orders()
    if not orders:
        await callback.answer("Нет данных для экспорта.", show_alert=True)
        return
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Заказы"
    headers = ["ID", "User ID", "Username", "Order Text", "Created At", "Sent At", "Received At", "Status"]
    sheet.append(headers)
    for order in orders:
        formatted_order = list(order)
        if formatted_order[4]:
            formatted_order[4] = datetime.fromisoformat(formatted_order[4]).strftime('%Y-%m-%d %H:%M:%S')
        if formatted_order[5]:
            formatted_order[5] = datetime.fromisoformat(formatted_order[5]).strftime('%Y-%m-%d %H:%M:%S')
        if formatted_order[6]:
            formatted_order[6] = datetime.fromisoformat(formatted_order[6]).strftime('%Y-%m-%d %H:%M:%S')
        sheet.append(formatted_order)
    excel_file = BytesIO()
    workbook.save(excel_file)
    excel_file.seek(0)
    await callback.message.answer_document(
        types.BufferedInputFile(excel_file.getvalue(), filename=f"orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"),
        caption="Ваш список заказов в формате Excel."
    )
    await callback.answer("Файл Excel создан и отправлен.")

@admin_router.callback_query(F.data == "admin_back_to_list", F.from_user.id.in_(ADMIN_IDS))
async def callback_back_to_list(callback: types.CallbackQuery):
    orders = get_all_orders()
    response = format_orders_list(orders)
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🔍 Посмотреть все", callback_data="admin_view_all_orders")],
        [types.InlineKeyboardButton(text="📊 Экспорт в Excel", callback_data="admin_export_excel")]
    ])
    await callback.message.edit_text(response, reply_markup=markup, parse_mode='HTML')
    await callback.answer()