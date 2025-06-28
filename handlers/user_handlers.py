# handlers/user_handlers.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import logging

from db import add_new_order, get_active_help_message_from_db, get_user_orders_paginated, \
    count_user_orders  # <-- ДОБАВЬ ЭТИ ФУНКЦИИ
from config import ORDERS_PER_PAGE, ORDER_STATUS_MAP
from models import Order, HelpMessage

from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

logger = logging.getLogger(__name__)

# Создаем роутер для обработки пользовательских команд и коллбэков
user_router = Router()


# Определяем состояния для процесса оформления заказа (этот код уже должен быть)
class OrderStates(StatesGroup):
    waiting_for_order_text = State()
    waiting_for_full_name = State()
    waiting_for_delivery_address = State()
    waiting_for_payment_method = State()
    waiting_for_contact_phone = State()
    waiting_for_delivery_notes = State()
    confirm_order = State()


class UserHandlers:
    """
    Класс для обработки команд и взаимодействий обычных пользователей.
    """

    DISPLAY_FIELD_NAMES = {
        'order_text': 'текст заказа',  # Добавим и для текста заказа, хоть он и обрабатывается отдельно
        'full_name': 'полное имя',
        'delivery_address': 'адрес доставки',
        'payment_method': 'способ оплаты',  # Добавим и для способа оплаты
        'contact_phone': 'контактный телефон',
        'delivery_notes': 'примечания к доставке'
    }

    @user_router.message(Command("start"))
    async def start_command(message: Message):
        """
        Обрабатывает команду /start.
        Отправляет приветственное сообщение и главное меню с инлайн-кнопками.
        """
        logger.info(f"Получена команда /start от пользователя {message.from_user.id}")

        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Сделать заказ 📝", callback_data="make_order")
        keyboard.button(text="Посмотреть мои заказы 📦", callback_data="view_my_orders")
        keyboard.button(text="Помощь ❓", callback_data="get_help")
        keyboard.adjust(1)  # Размещаем кнопки по одной в ряд

        await message.answer(
            "Привет! Я твой бот для оформления заказов. Что ты хочешь сделать?",
            reply_markup=keyboard.as_markup()
        )

    @user_router.callback_query(F.data == "make_order")
    async def make_order_callback(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает нажатие инлайн-кнопки "Сделать заказ".
        Переводит пользователя в состояние ожидания текста заказа.
        """
        logger.info(f"Пользователь {callback.from_user.id} нажал 'Введите заказ: '")
        await callback.message.edit_text("Введите заказ: 📝")
        await state.set_state(OrderStates.waiting_for_order_text)  # Устанавливаем состояние
        await callback.answer()

    @user_router.message(OrderStates.waiting_for_order_text)
    async def process_order_text(message: Message, state: FSMContext):
        """
        Обрабатывает ввод пользователем основного текста заказа.
        Предлагает подтвердить или отменить.
        """
        logger.info(f"Пользователь {message.from_user.id} ввел текст заказа.")
        await state.update_data(order_text=message.text)  # Сохраняем данные в FSM контекст

        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Подтвердить ✅", callback_data="confirm_input:full_name")  # Переходим к следующему полю
        keyboard.button(text="Отменить ❌", callback_data="cancel_order")
        keyboard.adjust(2)

        await message.answer(
            f"Твой заказ: *{message.text}*\n\nВсё верно? Подтверди, чтобы перейти к следующему шагу, или отмени заказ.",
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"  # Используем Markdown для выделения текста
        )

    # Обработчики для последовательного сбора данных
    @user_router.callback_query(F.data.startswith("confirm_input:"))
    async def confirm_input_and_next(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает подтверждение ввода и запрашивает следующее поле.
        """
        field_to_ask = callback.data.split(":")[1]
        user_data = await state.get_data()
        logger.info(f"Пользователь {callback.from_user.id} подтвердил ввод для {field_to_ask}. Данные: {user_data}")

        prompts = {
            "full_name": "Теперь введи своё **полное имя** (ФИО) 👤:",
            "delivery_address": "Укажи **адрес доставки** (город, улица, дом, квартира) 🏠:",
            "payment_method": "Выбери **способ оплаты** (например, 'наличные', 'картой') 💵:",
            "contact_phone": "Введи **контактный телефон** 📞:",
            "delivery_notes": "Если есть **примечания к доставке** (например, 'домофон 123'), напиши их. Если нет, можешь отправить `-` или `нет` 💬:"
        }

        if field_to_ask == "full_name":
            await callback.message.edit_text(prompts["full_name"], parse_mode="Markdown")
            await state.set_state(OrderStates.waiting_for_full_name)
        elif field_to_ask == "delivery_address":
            await callback.message.edit_text(prompts["delivery_address"], parse_mode="Markdown")
            await state.set_state(OrderStates.waiting_for_delivery_address)
        elif field_to_ask == "payment_method":
            payment_keyboard = InlineKeyboardBuilder()
            payment_keyboard.button(text="Наличные 💰", callback_data="set_payment_method:Наличные")
            payment_keyboard.button(text="Картой при получении 💳",
                                    callback_data="set_payment_method:Картой при получении")
            payment_keyboard.adjust(1)

            await callback.message.edit_text(
                "Как ты предпочитаешь **оплатить заказ**? 💳",
                reply_markup=payment_keyboard.as_markup(),
                parse_mode="Markdown"
            )
            await state.set_state(OrderStates.waiting_for_payment_method)
        elif field_to_ask == "contact_phone":
            await callback.message.edit_text(prompts["contact_phone"], parse_mode="Markdown")
            await state.set_state(OrderStates.waiting_for_contact_phone)
        elif field_to_ask == "delivery_notes":
            await callback.message.edit_text(prompts["delivery_notes"], parse_mode="Markdown")
            await state.set_state(OrderStates.waiting_for_delivery_notes)
        elif field_to_ask == "final_confirm":  # Этот кейс будет вызван после delivery_notes
            await UserHandlers.show_order_summary(callback.message, state)

        await callback.answer()

    # Обработчики для каждого поля с проверкой и подтверждением
    @user_router.message(OrderStates.waiting_for_full_name)
    @user_router.message(OrderStates.waiting_for_delivery_address)
    @user_router.message(OrderStates.waiting_for_contact_phone)
    @user_router.message(OrderStates.waiting_for_delivery_notes)
    async def process_order_field(message: Message, state: FSMContext):
        """
        Общий обработчик для полей заказа (ФИО, адрес, телефон, примечания).
        Сохраняет введенные данные и предлагает подтвердить или отменить.
        """
        current_state_str = await state.get_state()  # Получаем строковое представление текущего состояния

        # Определяем имя поля, соответствующее текущему состоянию
        field_mapping = {
            'OrderStates:waiting_for_full_name': 'full_name',
            'OrderStates:waiting_for_delivery_address': 'delivery_address',
            'OrderStates:waiting_for_contact_phone': 'contact_phone',
            'OrderStates:waiting_for_delivery_notes': 'delivery_notes',
        }

        # Получаем имя поля для сохранения, используя маппинг
        field_to_save = field_mapping.get(current_state_str)

        if field_to_save:
            await state.update_data(**{field_to_save: message.text})
            logger.info(f"Пользователь {message.from_user.id} ввел {field_to_save}: {message.text}")
        else:
            logger.error(f"Неизвестное состояние {current_state_str} для сохранения данных.")
            await message.answer(
                "Произошла ошибка при сохранении данных. Пожалуйста, попробуйте начать заново через /start.")
            await state.clear()
            return

        # Определяем следующее поле для запроса или завершение
        # Здесь мы используем строковые названия состояний из OrderStates.
        # Это для того, чтобы последовательность сохранялась.
        next_field_logic = {
            "waiting_for_full_name": "delivery_address",  # После ФИО идет адрес
            "waiting_for_delivery_address": "payment_method",  # После адреса - оплата (которая теперь кнопки)
            "waiting_for_contact_phone": "delivery_notes",  # После телефона - примечания
            "waiting_for_delivery_notes": "final_confirm"  # После примечаний - окончательное подтверждение
        }

        current_step_name = current_state_str.split(':')[-1]
        next_field = next_field_logic.get(current_step_name)

        keyboard = InlineKeyboardBuilder()
        if next_field:
            # Если следующее поле - это способ оплаты, то не даем кнопку "подтвердить",
            # а просто ждем ввода для следующего текстового поля.
            # Новая логика payment_method обрабатывается в confirm_input_and_next.
            keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field}")
        else:
            keyboard.button(text="Подтвердить ✅", callback_data="confirm_input:final_confirm")

        keyboard.button(text="Отменить ❌", callback_data="cancel_order")
        keyboard.adjust(2)

        # Более читабельный текст для пользователя
        display_field_name = UserHandlers.DISPLAY_FIELD_NAMES.get(field_to_save, field_to_save.replace('_', ' '))

        await message.answer(
            f"*{display_field_name.capitalize()}*: *{message.text}*\n\nВсё верно?",
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )

    # Добавь новый обработчик для выбора способа оплаты
    @user_router.callback_query(F.data.startswith("set_payment_method:"))
    async def set_payment_method(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает выбор способа оплаты с помощью инлайн-кнопок.
        Сохраняет выбранный способ и переходит к запросу контактного телефона.
        """
        payment_method = callback.data.split(":")[1]
        await state.update_data(payment_method=payment_method)
        logger.info(f"Пользователь {callback.from_user.id} выбрал способ оплаты: {payment_method}")

        # Переходим к следующему шагу: запрос контактного телефона
        await callback.message.edit_text(
            f"Ты выбрал способ оплаты: *{payment_method}*.\n\nТеперь введи свой **контактный телефон** 📞:",
            parse_mode="Markdown")
        await state.set_state(OrderStates.waiting_for_contact_phone)
        await callback.answer()

    @user_router.callback_query(F.data == "cancel_order")
    async def cancel_order(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает отмену заказа на любом этапе.
        Сбрасывает состояние и очищает данные.
        """
        logger.info(f"Пользователь {callback.from_user.id} отменил заказ.")
        await state.clear()  # Сбрасываем все состояния и данные
        await callback.message.edit_text("Оформление заказа отменено. Если хочешь начать заново, нажми /start.")
        await callback.answer()

    @staticmethod
    async def show_order_summary(message: Message, state: FSMContext):
        """
        Показывает пользователю полную сводку заказа для окончательного подтверждения.
        """
        user_data = await state.get_data()

        order_summary_parts = []
        for key, display_name in UserHandlers.DISPLAY_FIELD_NAMES.items():
            value = user_data.get(key)
            if value:  # Если значение есть, добавляем его в сводку
                order_summary_parts.append(f"*{display_name.capitalize()}*: {value}")
            elif key == 'delivery_notes':  # Примечания могут быть пустыми, но мы хотим их показать как "Нет"
                order_summary_parts.append(f"*{display_name.capitalize()}*: Нет")

        order_summary = "**Окончательная информация о заказе:**\n\n" + "\n".join(
            order_summary_parts) + "\n\nВсё верно? Подтверди заказ или отмени его."

        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Подтвердить и отправить ✅", callback_data="final_confirm_order")
        keyboard.button(text="Отменить заказ ❌", callback_data="cancel_order")
        keyboard.adjust(1)

        await message.answer(
            order_summary,
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )
        await state.set_state(OrderStates.confirm_order)  # Переходим в состояние окончательного подтверждения

    @user_router.callback_query(F.data == "final_confirm_order")
    async def final_confirm_order(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает окончательное подтверждение заказа пользователем.
        Сохраняет заказ в базу данных и очищает состояние.
        """
        user_data = await state.get_data()
        logger.info(f"Пользователь {callback.from_user.id} окончательно подтвердил заказ.")

        # Собираем данные для передачи в функцию БД
        order_to_save = {
            'user_id': callback.from_user.id,
            'username': callback.from_user.username or callback.from_user.full_name,
            'order_text': user_data.get('order_text'),
            'full_name': user_data.get('full_name'),
            'delivery_address': user_data.get('delivery_address'),
            'payment_method': user_data.get('payment_method'),
            'contact_phone': user_data.get('contact_phone'),
            'delivery_notes': user_data.get('delivery_notes'),
        }

        # Вызываем функцию из db.py для сохранения заказа
        new_order = await add_new_order(order_to_save)  # <-- ИЗМЕНЕНО

        await callback.message.edit_text(
            f"✅ Твой заказ №*{new_order.id}* успешно оформлен! Мы свяжемся с тобой в ближайшее время.",
            parse_mode="Markdown"
        )
        await state.clear()
        await callback.answer()

    @user_router.callback_query(F.data == "view_my_orders")
    async def view_my_orders_callback(callback: CallbackQuery, state: FSMContext):  # <-- Добавь state: FSMContext
        """
        Обрабатывает нажатие инлайн-кнопки "Посмотреть мои заказы".
        """
        logger.info(f"Пользователь {callback.from_user.id} нажал 'Посмотреть мои заказы'")
        # Вместо TODO и заглушки, вызываем нашу новую функцию
        await UserHandlers.show_user_orders(callback, state, page=0)  # <-- Вызываем функцию пагинации с первой страницы

    @staticmethod
    async def show_user_orders(message: Message | CallbackQuery, state: FSMContext, page: int = 0):
        """
        Показывает пользователю его заказы с пагинацией.
        """
        user_id = message.from_user.id
        offset = page * ORDERS_PER_PAGE

        user_orders = await get_user_orders_paginated(user_id, offset, ORDERS_PER_PAGE)
        total_orders = await count_user_orders(user_id)
        total_pages = (total_orders + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE  # Вычисляем общее количество страниц

        orders_list_text = f"**Твои заказы (страница {page + 1}/{total_pages if total_pages > 0 else 1}):**\n\n"

        if user_orders:
            for i, order in enumerate(user_orders):
                display_status = ORDER_STATUS_MAP.get(order.status, order.status)
                orders_list_text += (
                    f"**Заказ №{order.id}** (Статус: {display_status})\n"
                    f"  *Текст:* {order.order_text[:70]}...\n"
                    f"  *Дата:* {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
                )
                if i < len(user_orders) - 1:
                    orders_list_text += "---\n"  # Разделитель между заказами

            # Добавляем кнопки пагинации
            keyboard = InlineKeyboardBuilder()
            if page > 0:
                keyboard.button(text="⬅️ Назад", callback_data=f"my_orders_page:{page - 1}")
            if page < total_pages - 1:
                keyboard.button(text="Вперед ➡️", callback_data=f"my_orders_page:{page + 1}")
            keyboard.adjust(2)  # Выравниваем кнопки

            if isinstance(message, CallbackQuery):
                await message.message.edit_text(  # <-- ВОТ ГДЕ ОШИБКА БЫЛА! Нужен message.message
                    orders_list_text,
                    reply_markup=keyboard.as_markup(),
                    parse_mode="Markdown"
                )
            else:  # Это для объектов Message (как при команде /myorders)
                await message.answer(
                    orders_list_text,
                    reply_markup=keyboard.as_markup(),
                    parse_mode="Markdown"
                )

        else:
            if isinstance(message, CallbackQuery):
                await message.message.edit_text(
                    "У тебя пока нет заказов.",
                    parse_mode="Markdown"
                )
            else:  # Это для объектов Message
                await message.answer(
                    "У тебя пока нет заказов.",
                    parse_mode="Markdown"
                )

        await state.update_data(current_orders_page=page)  # Сохраняем текущую страницу
        if isinstance(message, CallbackQuery):
            await message.answer()  # Закрываем уведомление о нажатии кнопки

    @user_router.callback_query(F.data.startswith("my_orders_page:"))
    async def navigate_my_orders_page(callback: CallbackQuery, state: FSMContext):
        """
        Обрабатывает нажатия кнопок пагинации для заказов пользователя.
        """
        page = int(callback.data.split(":")[1])
        logger.info(f"Пользователь {callback.from_user.id} перешел на страницу {page} заказов.")
        await UserHandlers.show_user_orders(callback, state, page)

    @user_router.callback_query(F.data == "get_help")
    async def get_help_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие инлайн-кнопки "Помощь".
        Отправляет пользователю заранее заданное сообщение помощи.
        """
        logger.info(f"Пользователь {callback.from_user.id} запросил помощь.")

        # Используем новую функцию из db.py для получения активного сообщения
        active_message = await get_active_help_message_from_db()  # <-- ИЗМЕНЕНО

        if active_message:
            await callback.message.edit_text(active_message.message_text, parse_mode="Markdown")
        else:
            await callback.message.edit_text("Извини, сообщение помощи пока не настроено.")

        await callback.answer()
