import logging
import re
from typing import Union  # Для Type Hinting
import html  # Импортируем модуль для экранирования HTML

from aiogram import Router, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import (
    Message,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode  # Явный импорт ParseMode

from db import add_new_order
from config import (
    DISPLAY_FIELD_NAMES,
    ORDER_FIELDS_CONFIG,
    ORDER_FIELD_MAP,
    PHONE_NUMBER_REGEX
)
from .user_states import OrderStates
from .user_utils import _display_user_main_menu  # Исправлен импорт, было main_menu

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "make_order")
async def make_order_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие инлайн-кнопки "Сделать заказ".
    Начинает процесс оформления заказа, запрашивая первое поле из конфигурации.
    """
    logger.info(f"Пользователь {callback.from_user.id} нажал 'Сделать заказ'.")

    # Получаем конфигурацию для первого поля (order_text)
    first_field_config = ORDER_FIELDS_CONFIG[0]

    await callback.message.edit_text(first_field_config["prompt"], parse_mode=ParseMode.HTML)
    # Устанавливаем состояние, используя getattr для получения объекта состояния по имени
    await state.set_state(getattr(OrderStates, first_field_config["state_name"]))
    await callback.answer()


@router.message(OrderStates.waiting_for_order_text)
async def process_order_text(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователя для основного текста заказа.
    Предлагает подтверждение или отмену, переходя к следующему полю (full_name).
    """
    logger.info(f"Пользователь {message.from_user.id} ввел текст заказа.")
    await state.update_data(order_text=message.text)

    current_field_config = ORDER_FIELD_MAP.get("order_text")
    if not current_field_config:
        logger.error("Конфигурация для 'order_text' не найдена.")
        await message.answer(
            "Произошла ошибка в процессе оформления заказа. Пожалуйста, попробуйте снова через /start.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return

    next_field_key = current_field_config.get("next_field")
    if not next_field_key:
        logger.error("Следующее поле для 'order_text' не определено в конфиге.")
        await message.answer(
            "Произошла ошибка в процессе оформления заказа. Пожалуйста, попробуйте снова через /start.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    escaped_text = html.escape(message.text)
    await message.answer(
        f"Твой заказ: <b>{escaped_text}</b>\n\nВсё верно? Подтверди, чтобы перейти к следующему шагу, или отмени заказ.",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data.startswith("confirm_input:"))
async def confirm_input_and_next(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает подтверждение ввода предыдущего поля и запрашивает следующее поле.
    Использует ORDER_FIELD_MAP для динамической генерации запроса.
    """
    # Извлекаем ключ следующего поля из callback_data. Пример: "confirm_input:full_name"
    field_to_ask_key = callback.data.split(":")[1]
    user_data = await state.get_data()
    logger.info(
        f"Пользователь {callback.from_user.id} подтвердил ввод. Запрашивается: {field_to_ask_key}. Данные: {user_data}")

    # Если это окончательное подтверждение перед показом сводки
    if field_to_ask_key == "final_confirm":
        await _show_order_summary(callback.message, state)
        await callback.answer()
        return

    next_field_config = ORDER_FIELD_MAP.get(field_to_ask_key)

    if not next_field_config:
        logger.error(f"Конфигурация для поля '{field_to_ask_key}' не найдена.")
        await callback.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте снова через /start.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        await callback.answer()
        return

    input_type = next_field_config.get("input_type")
    prompt_text = next_field_config["prompt"]
    state_to_set = getattr(OrderStates, next_field_config["state_name"])

    if input_type == "text":
        await callback.message.edit_text(prompt_text, parse_mode=ParseMode.HTML)
        await state.set_state(state_to_set)
    elif input_type == "buttons":
        keyboard = InlineKeyboardBuilder()
        for text, data_value in next_field_config["options"].items():
            keyboard.button(text=text, callback_data=f"set_{field_to_ask_key}:{data_value}")
        keyboard.adjust(1)  # Всегда одна кнопка в ряду для кнопочного ввода
        await callback.message.edit_text(
            prompt_text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(state_to_set)
    elif input_type == "contact_button":
        reply_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        # Удаляем предыдущее инлайн-сообщение
        await callback.message.delete()
        # Отправляем новое сообщение с Reply-клавиатурой
        await callback.message.answer(
            prompt_text,
            reply_markup=reply_keyboard,
            parse_mode=ParseMode.HTML
        )
        await state.set_state(state_to_set)
    else:
        logger.error(f"Неизвестный тип ввода '{input_type}' для поля '{field_to_ask_key}'.")
        await callback.message.edit_text(
            "Произошла ошибка при определении типа ввода. Пожалуйста, попробуйте снова через /start.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()

    await callback.answer()


@router.message(OrderStates.waiting_for_full_name)
async def process_full_name_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователя для полного имени.
    Сохраняет данные, предлагает подтверждение и переходит к следующему шагу.
    """
    await state.update_data(full_name=message.text)
    logger.info(f"Пользователь {message.from_user.id} ввел полное имя: {message.text}")

    current_field_config = ORDER_FIELD_MAP.get("full_name")
    next_field_key = current_field_config.get("next_field")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    display_field_name = DISPLAY_FIELD_NAMES.get("full_name", "Полное имя")

    escaped_text = html.escape(message.text)
    await message.answer(
        f"<b>{display_field_name.capitalize()}</b>: <b>{escaped_text}</b>\n\nВсё верно?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.message(OrderStates.waiting_for_delivery_address)
async def process_delivery_address_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователя для адреса доставки.
    Сохраняет данные, предлагает подтверждение и переходит к следующему шагу.
    """
    await state.update_data(delivery_address=message.text)
    logger.info(f"Пользователь {message.from_user.id} ввел адрес доставки: {message.text}")

    current_field_config = ORDER_FIELD_MAP.get("delivery_address")
    next_field_key = current_field_config.get("next_field")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    display_field_name = DISPLAY_FIELD_NAMES.get("delivery_address", "Адрес доставки")

    escaped_text = html.escape(message.text)
    await message.answer(
        f"<b>{display_field_name.capitalize()}</b>: <b>{escaped_text}</b>\n\nВсё верно?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.message(OrderStates.waiting_for_delivery_notes)
async def process_delivery_notes_input(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователя для примечаний к доставке.
    Сохраняет данные, предлагает подтверждение и переходит к следующему шагу (окончательное подтверждение).
    """
    await state.update_data(delivery_notes=message.text)
    logger.info(f"Пользователь {message.from_user.id} ввел примечания к доставке: {message.text}")

    current_field_config = ORDER_FIELD_MAP.get("delivery_notes")
    next_field_key = current_field_config.get("next_field")  # Ожидается "final_confirm"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    display_field_name = DISPLAY_FIELD_NAMES.get("delivery_notes", "Примечания к доставке")

    escaped_text = html.escape(message.text)
    await message.answer(
        f"<b>{display_field_name.capitalize()}</b>: <b>{escaped_text}</b>\n\nВсё верно?",
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.message(OrderStates.waiting_for_contact_phone)
async def process_contact_phone(message: Message, state: FSMContext):
    """
    Обрабатывает ввод контактного телефона. Принимает как текстовый ввод, так и контакт через кнопку.
    Проверяет формат для ручного ввода.
    """
    contact_phone = None
    user_id = message.from_user.id

    # Сначала проверяем, был ли отправлен контакт через кнопку
    if message.contact and message.contact.user_id == user_id:
        contact_phone = message.contact.phone_number
        logger.info(f"Пользователь {user_id} отправил номер телефона через кнопку: {contact_phone}")
        # Reply-клавиатура автоматически убирается Telegram
    elif message.text:
        # Проверяем формат для ручного ввода
        if re.fullmatch(PHONE_NUMBER_REGEX, message.text):
            contact_phone = message.text
            logger.info(f"Пользователь {user_id} ввел номер телефона вручную: {contact_phone}")
            # Убираем Reply-клавиатуру, отправляя новое сообщение с пустой клавиатурой
            await message.answer("Спасибо, обрабатываем...", reply_markup=ReplyKeyboardRemove())
        else:
            # Неверный формат - остаемся в этом же состоянии
            await message.answer(
                "Неверный формат номера телефона. Пожалуйста, используйте формат <code>+380XXXXXXXXX</code> или нажмите кнопку.",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                ),
                parse_mode=ParseMode.HTML
            )
            return  # Выход из хэндлера, чтобы не обновлять FSM-контекст

    if contact_phone:
        # Если телефон получен, обновляем состояние
        await state.update_data(contact_phone=contact_phone)

        # Переходим к следующему шагу - запросу примечаний
        next_field_config = ORDER_FIELD_MAP.get("contact_phone", {})
        next_field_key = next_field_config.get("next_field")

        # Формируем сообщение для подтверждения ТОЛЬКО номера телефона
        confirm_message_text = (
            f"<b>Контактный телефон:</b> {html.escape(contact_phone)}\n\n"
            f"Всё верно? Подтверди, чтобы перейти к следующему шагу, или нажми 'Отмена'."
        )

        # Создаем Inline-клавиатуру для подтверждения
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
        keyboard.button(text="Отменить ❌", callback_data="cancel_order")
        keyboard.adjust(2)

        # Отправляем НОВОЕ сообщение с Inline-клавиатурой
        await message.answer(
            text=confirm_message_text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.HTML
        )

        # Мы не переводим пользователя в следующее состояние здесь.
        # Переход произойдет, когда он нажмет "Подтвердить ✅".


@router.callback_query(F.data.startswith("set_payment_method:"))
async def set_payment_method(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор метода оплаты с помощью инлайн-кнопок.
    Сохраняет выбранный метод и переходит к запросу контактного телефона.
    """
    payment_method = callback.data.split(":")[1]
    await state.update_data(payment_method=payment_method)
    logger.info(f"Пользователь {callback.from_user.id} выбрал метод оплаты: {payment_method}")

    next_field_config_after_payment = ORDER_FIELD_MAP["payment_method"]
    next_field_key_after_payment = next_field_config_after_payment.get("next_field")
    contact_phone_config = ORDER_FIELD_MAP.get(next_field_key_after_payment)

    if not contact_phone_config:
        logger.error(
            f"Конфигурация для следующего поля '{next_field_key_after_payment}' не найдена после выбора метода оплаты.")
        await callback.message.edit_text(
            "Произошла ошибка. Пожалуйста, попробуйте снова через /start.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        await callback.answer()
        return

    reply_keyboard_for_phone = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await callback.message.delete()  # Удаляем сообщение с выбором метода оплаты
    await callback.message.answer(
        f"Ты выбрал способ оплаты: <b>{html.escape(payment_method)}</b>.\n\n" + contact_phone_config["prompt"],
        reply_markup=reply_keyboard_for_phone,
        parse_mode=ParseMode.HTML
    )
    await state.set_state(getattr(OrderStates, contact_phone_config["state_name"]))
    await callback.answer()


@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает отмену заказа на любой стадии.
    Сбрасывает состояние и очищает данные.
    """
    logger.info(f"Пользователь {callback.from_user.id} отменил заказ.")
    # Отправляем сообщение об отмене и пытаемся убрать Reply-клавиатуру, если она была активна
    await state.clear()
    await _display_user_main_menu(callback, state)
    await callback.answer()


async def _show_order_summary(update_object: Union[Message, CallbackQuery], state: FSMContext):
    """
    Показывает пользователю полную сводку заказа для окончательного подтверждения.
    Принимает Message или CallbackQuery и соответствующим образом отправляет/редактирует сообщение.
    """
    user_data = await state.get_data()

    order_summary_parts = []
    for field_config in ORDER_FIELDS_CONFIG:
        key = field_config["key"]
        display_name = DISPLAY_FIELD_NAMES.get(key, key.replace('_', ' '))
        value = user_data.get(key)

        # Экранируем пользовательские данные, чтобы они не ломали разметку
        escaped_value = html.escape(str(value)) if value is not None else None

        if escaped_value:
            order_summary_parts.append(f"<b>{display_name.capitalize()}</b>: {escaped_value}")
        elif key == 'delivery_notes':
            order_summary_parts.append(f"<b>{display_name.capitalize()}</b>: Нет")

    order_summary = "<b>Окончательная информация о заказе:</b>\n\n" + "\n".join(
        order_summary_parts) + "\n\nВсё верно? Подтверди заказ или отмени его."

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить и отправить ✅", callback_data="final_confirm_order")
    keyboard.button(text="Отменить заказ ❌", callback_data="cancel_order")
    keyboard.adjust(1)

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(
            order_summary,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    elif isinstance(update_object, CallbackQuery):
        await update_object.message.edit_text(
            order_summary,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        await update_object.answer()  # Отвечаем на callback


@router.callback_query(F.data == "final_confirm_order")
async def final_confirm_order(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает окончательное подтверждение заказа пользователем.
    Сохраняет заказ в базу данных и очищает состояние.
    """
    user_data = await state.get_data()
    logger.info(f"Пользователь {callback.from_user.id} окончательно подтвердил заказ.")

    # Используем username, если доступен, иначе полное имя, иначе ID пользователя
    username_to_save = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)

    new_order = await add_new_order(
        user_id=callback.from_user.id,
        username=username_to_save,
        order_text=user_data.get('order_text', 'Не указан'),  # Указываем дефолт, если вдруг нет
        full_name=user_data.get('full_name'),
        delivery_address=user_data.get('delivery_address'),
        payment_method=user_data.get('payment_method'),
        contact_phone=user_data.get('contact_phone'),
        delivery_notes=user_data.get('delivery_notes'),
    )

    await callback.message.edit_text(
        f"✅ Твой заказ №<b>{new_order.id}</b> успешно оформлен! Мы свяжемся с тобой в ближайшее время.",
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    await callback.answer()
