# handlers/user.py
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

# --- НОВЫЙ ИМПОРТ ДЛЯ ФИЛЬТРОВ ---
from aiogram.filters import Command, CommandStart # Импортируем Command и CommandStart

from database import add_order, get_order_by_id, get_user_orders
from config import ADMIN_IDS

user_router = Router()

class UserOrderState(StatesGroup):
    waiting_for_order_text = State()

@user_router.message(CommandStart()) # Используем CommandStart() для команды /start
@user_router.message(Command(commands=["help"])) # Используем Command() для команды /help
async def send_welcome(message: types.Message):
    """Отправляет приветственное сообщение и предлагает сделать заказ."""
    await message.reply("Привет! Я твой бот для заказов. Чтобы сделать заказ, просто отправь мне сообщение с описанием того, что ты хочешь заказать.")
    await message.bot.set_my_commands([
        types.BotCommand(command="start", description="Начать работу с ботом"),
        types.BotCommand(command="help", description="Получить помощь"),
        types.BotCommand(command="myorders", description="Показать мои заказы")
    ])

@user_router.message(Command(commands=["myorders"])) # Используем Command() для команды /myorders
async def show_user_orders(message: types.Message):
    """Показывает пользователю список его заказов."""
    user_id = message.from_user.id
    orders = get_user_orders(user_id)

    if not orders:
        await message.reply("У тебя пока нет активных заказов.")
        return

    response = "<b>Твои заказы:</b>\n\n"
    for order in orders:
        order_id, _, _, order_text, created_at, sent_at, received_at, status = order
        truncated_text = (order_text[:50] + '...') if len(order_text) > 50 else order_text
        response += (f"📦 Заказ №{order_id}\n"
                     f"   Текст: {truncated_text}\n"
                     f"   Создан: {datetime.fromisoformat(created_at).strftime('%d.%m.%Y %H:%M')}\n"
                     f"   Статус: <b>{status}</b>\n\n")
    await message.reply(response, parse_mode='HTML')

@user_router.message(F.text & ~F.text.startswith('/'))
async def handle_new_order(message: types.Message):
    """Обрабатывает любое текстовое сообщение, которое не является командой, как новый заказ."""

    user_id = message.from_user.id
    username = message.from_user.full_name or message.from_user.username or "Неизвестный пользователь"
    order_text = message.text

    order_id = add_order(user_id, username, order_text)

    await message.reply(f"Спасибо! Твой заказ №{order_id} принят. Мы свяжемся с тобой в ближайшее время.")

    for admin_id in ADMIN_IDS:
        try:
            current_order_data = get_order_by_id(order_id)
            if not current_order_data:
                print(f"Ошибка: Заказ с ID {order_id} не найден после добавления.")
                continue

            created_at_dt = datetime.fromisoformat(current_order_data[4])
            formatted_created_at = created_at_dt.strftime('%d.%m.%Y %H:%M')

            admin_message = (f"🎉 <b>Новый заказ №{order_id}</b>\n\n"
                             f"👤 От: {username} (ID: {user_id})\n"
                             f"📝 Текст заказа: {order_text}\n"
                             f"⏰ Время создания: {formatted_created_at}\n"
                             f"Статус: Новый")

            markup = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="👁️ Подробнее/Изменить", callback_data=f"admin_view_order_{order_id}")],
                [types.InlineKeyboardButton(text="✅ Принять заказ", callback_data=f"admin_status_Обрабатывается_{order_id}")]
            ])
            await message.bot.send_message(admin_id, admin_message, reply_markup=markup, parse_mode='HTML')
        except Exception as e:
            print(f"Не удалось отправить уведомление администратору {admin_id}: {e}")
