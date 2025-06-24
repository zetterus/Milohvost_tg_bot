# handlers/user.py
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from aiogram.filters import Command, CommandStart # Импортируем Command и CommandStart

from database import add_order, get_order_by_id, get_user_orders, update_order_delivery_info, update_order_status
from config import ADMIN_IDS

user_router = Router()

class UserOrderState(StatesGroup):
    waiting_for_order_text = State() # Ожидание заказа
    confirm_order = State() # Ожидание подтверждения/отмены заказа
    waiting_for_full_name = State() # Ожидание ФИО
    waiting_for_address = State()   # Ожидание адреса
    waiting_for_payment_method = State() # Ожидание способа оплаты
    waiting_for_phone = State() # Ожидание телефона
    waiting_for_notes = State() # Ожидание примечаний

@user_router.message(CommandStart())
@user_router.message(Command(commands=["help"]))
async def send_welcome(message: types.Message):
    """Отправляет приветственное сообщение и предлагает сделать заказ."""
    await message.reply("Привет! Я твой бот для заказов. Чтобы сделать заказ, просто отправь мне сообщение с описанием того, что ты хочешь заказать.")
    await message.bot.set_my_commands([
        types.BotCommand(command="start", description="Начать работу с ботом"),
        types.BotCommand(command="help", description="Получить помощь"),
        types.BotCommand(command="myorders", description="Показать мои заказы")
    ])

@user_router.message(Command(commands=["myorders"]))
async def show_user_orders(message: types.Message):
    """Показывает пользователю список его заказов."""
    user_id = message.from_user.id
    orders = get_user_orders(user_id)

    if not orders:
        await message.reply("У тебя пока нет активных заказов.")
        return

    response = "<b>Твои заказы:</b>\n\n"
    for order in orders:
        # Извлекаем все поля, включая новые, для отображения
        order_id, _, _, order_text, created_at, sent_at, received_at, status, \
        full_name, delivery_address, payment_method, contact_phone, delivery_notes = order

        truncated_text = (order_text[:50] + '...') if len(order_text) > 50 else order_text
        formatted_created_at = datetime.fromisoformat(created_at).strftime('%d.%m.%Y %H:%M')

        # Добавим информацию о доставке, если она есть
        delivery_info_str = ""
        if full_name: delivery_info_str += f"   ФИО: {full_name}\n"
        if delivery_address: delivery_info_str += f"   Адрес: {delivery_address}\n"
        if payment_method: delivery_info_str += f"   Оплата: {payment_method}\n"
        if contact_phone: delivery_info_str += f"   Телефон: {contact_phone}\n"
        if delivery_notes: delivery_info_str += f"   Примечания: {delivery_notes}\n"


        response += (f"📦 Заказ №{order_id}\n"
                     f"   Текст: {truncated_text}\n"
                     f"   Создан: {formatted_created_at}\n"
                     f"   Статус: <b>{status}</b>\n")
        if delivery_info_str:
            response += f"--- Детали доставки ---\n{delivery_info_str}"
        response += "\n" # Пустая строка для разделения заказов
    await message.reply(response, parse_mode='HTML')


@user_router.message(F.text & ~F.text.startswith('/'))
async def handle_new_order(message: types.Message, state: FSMContext):
    """
    Первый этап оформления заказа: пользователь вводит текст.
    Предлагает подтвердить или отменить.
    """
    user_id = message.from_user.id
    username = message.from_user.full_name or message.from_user.username or "Неизвестный пользователь"
    order_text = message.text

    # Сохраняем начальные данные в FSM context, но пока не в базу
    await state.update_data(user_id=user_id, username=username, order_text=order_text)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order")],
        [types.InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")]
    ])
    await message.reply(f"Ты хочешь заказать: \n\n<b>{order_text}</b>\n\nПодтвердить заказ или отменить?",
                        reply_markup=markup, parse_mode='HTML')
    await state.set_state(UserOrderState.confirm_order) # Переходим в состояние ожидания подтверждения

# --- Обработка подтверждения/отмены заказа ---
@user_router.callback_query(F.data == "confirm_order", UserOrderState.confirm_order)
async def process_confirm_order(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    order_text = user_data.get('order_text')
    user_id = user_data.get('user_id')
    username = user_data.get('username')

    # Создаем заказ в базе данных, но пока без деталей доставки
    order_id = add_order(user_id, username, order_text)
    await state.update_data(order_id=order_id) # Сохраняем ID заказа в FSM context

    await callback_query.message.edit_text("Отлично! Теперь давай уточним данные для доставки.\n\n"
                                           "Пожалуйста, введите свое полное ФИО:")
    await state.set_state(UserOrderState.waiting_for_full_name) # Переходим к запросу ФИО
    await callback_query.answer() # Закрываем уведомление о нажатии кнопки

@user_router.callback_query(F.data == "cancel_order", UserOrderState.confirm_order)
async def process_cancel_order(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear() # Очищаем все данные FSM
    await callback_query.message.edit_text("Заказ отменен. Если передумаешь, просто отправь новое сообщение.")
    await callback_query.answer()

# --- Шаги последовательного ввода данных для доставки ---

@user_router.message(UserOrderState.waiting_for_full_name, F.text)
async def process_full_name(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    await state.update_data(full_name=full_name)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Далее", callback_data="next_step_address")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order_delivery")]
    ])
    await message.reply(f"Твое ФИО: <b>{full_name}</b>\n\nВерно? Жми 'Далее' или 'Отменить заказ'.", parse_mode='HTML', reply_markup=markup)
    await state.set_state(UserOrderState.waiting_for_address) # Переходим к ожиданию подтверждения/адреса

@user_router.callback_query(F.data == "next_step_address", UserOrderState.waiting_for_address)
async def request_address(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Отлично! Теперь введите адрес доставки (улица, дом, квартира, город, индекс):")
    await callback_query.answer() # Закрываем уведомление
    # Состояние уже установлено в waiting_for_address предыдущим хэндлером, но для ясности можно повторить
    await state.set_state(UserOrderState.waiting_for_address)


@user_router.message(UserOrderState.waiting_for_address, F.text)
async def process_address(message: types.Message, state: FSMContext):
    address = message.text.strip()
    await state.update_data(delivery_address=address)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Далее", callback_data="next_step_payment_method")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order_delivery")]
    ])
    await message.reply(f"Адрес доставки: <b>{address}</b>\n\nВерно?", parse_mode='HTML', reply_markup=markup)
    await state.set_state(UserOrderState.waiting_for_payment_method)


@user_router.callback_query(F.data == "next_step_payment_method", UserOrderState.waiting_for_payment_method)
async def request_payment_method(callback_query: types.CallbackQuery, state: FSMContext):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💵 Наличные при получении", callback_data="payment_Наличные при получении")],
        [types.InlineKeyboardButton(text="💳 Онлайн-оплата (по запросу)", callback_data="payment_Онлайн-оплата")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order_delivery")]
    ])
    await callback_query.message.edit_text("Выберите способ оплаты:", reply_markup=markup)
    await callback_query.answer()
    await state.set_state(UserOrderState.waiting_for_payment_method)


@user_router.callback_query(F.data.startswith("payment_"), UserOrderState.waiting_for_payment_method)
async def process_payment_method_callback(callback_query: types.CallbackQuery, state: FSMContext):
    payment_method = callback_query.data.split('_', 1)[1] # Извлекаем часть после 'payment_'
    await state.update_data(payment_method=payment_method)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Далее", callback_data="next_step_phone")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order_delivery")]
    ])
    await callback_query.message.edit_text(f"Способ оплаты: <b>{payment_method}</b>\n\nВерно?", parse_mode='HTML', reply_markup=markup)
    await callback_query.answer()
    await state.set_state(UserOrderState.waiting_for_phone) # Переходим к запросу телефона


@user_router.callback_query(F.data == "next_step_phone", UserOrderState.waiting_for_phone)
async def request_phone(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Введите ваш контактный номер телефона:")
    await callback_query.answer()
    await state.set_state(UserOrderState.waiting_for_phone)


@user_router.message(UserOrderState.waiting_for_phone, F.text)
async def process_phone(message: types.Message, state: FSMContext):
    contact_phone = message.text.strip()
    await state.update_data(contact_phone=contact_phone)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Далее", callback_data="next_step_notes")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order_delivery")]
    ])
    await message.reply(f"Контактный телефон: <b>{contact_phone}</b>\n\nВерно?", parse_mode='HTML', reply_markup=markup)
    await state.set_state(UserOrderState.waiting_for_notes)


@user_router.callback_query(F.data == "next_step_notes", UserOrderState.waiting_for_notes)
async def request_notes(callback_query: types.CallbackQuery, state: FSMContext):
    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="Пропустить", callback_data="finish_order")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order_delivery")]
    ])
    await callback_query.message.edit_text("Есть ли какие-либо примечания к доставке? (например, 'домофон не работает', 'позвонить заранее')\n\nЕсли нет, нажмите 'Пропустить'.", reply_markup=markup)
    await callback_query.answer()
    await state.set_state(UserOrderState.waiting_for_notes)


@user_router.message(UserOrderState.waiting_for_notes, F.text)
async def process_notes(message: types.Message, state: FSMContext):
    delivery_notes = message.text.strip()
    await state.update_data(delivery_notes=delivery_notes)

    markup = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Завершить оформление", callback_data="finish_order")],
        [types.InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order_delivery")]
    ])
    await message.reply(f"Примечания: <b>{delivery_notes}</b>\n\nВерно? Нажмите 'Завершить оформление'.", parse_mode='HTML', reply_markup=markup)
    await state.set_state(UserOrderState.waiting_for_notes) # Остаемся в этом состоянии, пока не будет финализация


@user_router.callback_query(F.data == "finish_order", UserOrderState.waiting_for_notes)
async def finalize_order(callback_query: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    order_id = user_data.get('order_id')

    # Обновляем заказ в базе данных всеми собранными деталями
    update_order_delivery_info(
        order_id,
        full_name=user_data.get('full_name'),
        delivery_address=user_data.get('delivery_address'),
        payment_method=user_data.get('payment_method'),
        contact_phone=user_data.get('contact_phone'),
        delivery_notes=user_data.get('delivery_notes')
    )

    await callback_query.message.edit_text(f"🚀 Ваш заказ №{order_id} полностью оформлен и принят!\nМы свяжемся с вами в ближайшее время для подтверждения деталей.")

    # Отправляем уведомление администраторам с полными деталями
    order = get_order_by_id(order_id) # Получаем обновленные данные
    if order:
        order_id, user_id, username, order_text, created_at_iso, sent_at_iso, received_at_iso, status, \
        full_name, delivery_address, payment_method, contact_phone, delivery_notes = order

        created_at_dt = datetime.fromisoformat(created_at_iso)
        formatted_created_at = created_at_dt.strftime('%d.%m.%Y %H:%M')

        admin_message = (f"🎉 <b>НОВЫЙ ОФОРМЛЕННЫЙ ЗАКАЗ №{order_id}</b>\n\n"
                         f"👤 От: {username} (ID: <code>{user_id}</code>)\n"
                         f"📝 Текст заказа: {order_text}\n"
                         f"⏰ Время создания: {formatted_created_at}\n"
                         f"Статус: <b>{status}</b>\n\n"
                         f"--- Детали доставки ---\n"
                         f"ФИО: {full_name or 'Не указано'}\n"
                         f"Адрес: {delivery_address or 'Не указано'}\n"
                         f"Оплата: {payment_method or 'Не указано'}\n"
                         f"Телефон: {contact_phone or 'Не указано'}\n"
                         f"Примечания: {delivery_notes or 'Нет'}")

        markup = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="👁️ Подробнее/Изменить", callback_data=f"admin_view_order_{order_id}")],
            [types.InlineKeyboardButton(text="✅ Принять заказ", callback_data=f"admin_status_Обрабатывается_{order_id}")]
        ])

        for admin_id in ADMIN_IDS:
            try:
                await callback_query.bot.send_message(admin_id, admin_message, reply_markup=markup, parse_mode='HTML')
            except Exception as e:
                print(f"Не удалось отправить уведомление администратору {admin_id}: {e}")
    else:
        print(f"Ошибка: Заказ {order_id} не найден при финализации.")
        await callback_query.message.answer("Произошла ошибка при финализации заказа. Администратор уведомлен.")

    await state.clear() # Очищаем FSM после завершения
    await callback_query.answer()


@user_router.callback_query(F.data == "cancel_order_delivery")
async def cancel_order_delivery(callback_query: types.CallbackQuery, state: FSMContext):
    # Если заказ уже был добавлен в БД, мы можем отменить его или удалить.
    # Здесь мы просто очищаем FSM и сообщаем пользователю.
    # Если ты хочешь удалять из БД, добавь соответствующую функцию в database.py
    # или менять статус на "Отменен".
    user_data = await state.get_data()
    order_id = user_data.get('order_id')
    if order_id:
        # Можно обновить статус заказа на "Отменен" в базе данных, если он уже создан
        update_order_status(order_id, "Отменен")
        await callback_query.message.edit_text(f"Заказ №{order_id} отменен. Если передумаешь, просто отправь новое сообщение.")
    else:
        await callback_query.message.edit_text("Оформление заказа отменено. Если передумаешь, просто отправь новое сообщение.")

    await state.clear()
    await callback_query.answer()

# --- Логика для отмены диалога в любой момент (если пользователь вводит текст, когда ожидается кнопка) ---
@user_router.message(F.text, UserOrderState) # Ловим любой текст, когда пользователь находится в любом FSM состоянии
async def handle_unexpected_text_during_fsm(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state: # Если пользователь в FSM, но не в состоянии ожидания текста заказа
        if current_state != UserOrderState.waiting_for_order_text:
            markup = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="❌ Отменить оформление", callback_data="cancel_order_delivery")]
            ])
            await message.reply("Кажется, ты ввел что-то неожиданное. Пожалуйста, следуй инструкциям.\n\n"
                                f"Текущий этап: {current_state.split(':')[-1]}\n\n"
                                "Ты можешь отменить оформление заказа в любой момент.", reply_markup=markup)
            return
    # Если это waiting_for_order_text, то это обработает handle_new_order
    # Если это сообщение не в FSM, оно также будет проигнорировано этим хэндлером
