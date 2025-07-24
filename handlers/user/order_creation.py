import logging
from typing import Union
import html

from aiogram import Router, F, Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.types import (
    Message,
    CallbackQuery,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from db import add_new_order, get_or_create_user # Добавлен get_or_create_user для получения username
from config import (
    ORDER_FIELDS_CONFIG,
    ORDER_FIELD_MAP,
    PHONE_NUMBER_REGEX,
    ORDER_FIELD_NAMES_KEYS
)
from .user_states import OrderStates
from .user_utils import _display_user_main_menu, send_new_order_notification_to_admins, send_user_notification # Добавлен импорт send_user_notification
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "make_order")
async def make_order_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает нажатие инлайн-кнопки "Сделать заказ".
    Начинает процесс оформления заказа, запрашивая первое поле из конфигурации.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} нажал 'Сделать заказ'.")

    # Получаем конфигурацию для первого поля (order_text)
    first_field_config = ORDER_FIELDS_CONFIG[0]

    # Устанавливаем состояние для первого поля
    await state.set_state(getattr(OrderStates, first_field_config["state_name"]))
    # Сохраняем ключ текущего поля в FSM, чтобы знать, какое поле сейчас обрабатывается
    await state.update_data(current_field_key=first_field_config["key"])

    # Используем prompt_key для получения локализованного текста запроса
    prompt_text = get_localized_message(first_field_config["prompt_key"], lang)

    await callback.message.edit_text(prompt_text, parse_mode=ParseMode.HTML)
    await callback.answer()


async def _request_next_field(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        lang: str,
        next_field_key: str
):
    """
    Вспомогательная функция для запроса следующего поля.
    """
    user_data = await state.get_data()
    user_id = update_object.from_user.id # Добавлено для логирования

    logger.info(f"Пользователь {user_id}: Запрос следующего поля. next_field_key: {next_field_key}") # Добавлено логирование

    if next_field_key == "final_confirm":
        logger.info(f"Пользователь {user_id}: Переход к окончательному подтверждению заказа.") # Добавлено логирование
        # Переходим к окончательному подтверждению
        await state.set_state(OrderStates.confirm_order)
        # Формируем окончательное резюме заказа
        summary_text = get_localized_message("final_order_summary_title", lang) + "\n\n"

        for field_conf in ORDER_FIELDS_CONFIG:
            key = field_conf["key"]
            value = user_data.get(key)

            # Локализованное название поля
            field_name = get_localized_message(ORDER_FIELD_NAMES_KEYS.get(key, key), lang)

            # Специальная обработка для payment_method
            if key == "payment_method" and value:
                payment_options = ORDER_FIELD_MAP.get("payment_method", {}).get("options_keys", {})
                # Ищем ключ локализации для выбранного значения
                localized_payment_method_key = next((k for k, v in payment_options.items() if v == value), None)
                if localized_payment_method_key:
                    value = get_localized_message(localized_payment_method_key, lang)

            # Специальная обработка для delivery_notes
            if key == "delivery_notes" and (
                    value is None or str(value).strip() == '-' or str(value).strip().lower() == get_localized_message(
                    "no_notes_keyword", lang).lower()):
                value = get_localized_message("no_notes_display", lang)

            # Экранируем HTML в пользовательском вводе
            escaped_value = html.escape(str(value)) if value is not None else get_localized_message("not_specified",
                                                                                                    lang)

            if key == "order_text":  # Для текста заказа используем <code>
                summary_text += f"<b>{field_name.capitalize()}</b>:\n<code>{escaped_value}</code>\n"
            else:
                summary_text += f"<b>{field_name.capitalize()}</b>: {escaped_value}\n"

        summary_text += "\n" + get_localized_message("final_order_summary_confirmation", lang)

        keyboard = InlineKeyboardBuilder()
        keyboard.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang),
                                          callback_data="final_confirm_order"))
        keyboard.row(
            InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
        keyboard.adjust(1)
        reply_markup = keyboard.as_markup()

        # Отправляем окончательное подтверждение
        if isinstance(update_object, Message):
            await update_object.answer(summary_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        elif isinstance(update_object, CallbackQuery):
            await update_object.message.edit_text(summary_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            await update_object.answer()
        return

    # Переходим к следующему полю
    next_field_config = ORDER_FIELD_MAP.get(next_field_key)
    if not next_field_config:
        logger.error(f"Пользователь {user_id}: Не найдена конфигурация для следующего поля: {next_field_key}. Возврат в главное меню.") # Добавлено логирование
        await _display_user_main_menu(update_object, state, lang=lang)
        return

    await state.set_state(getattr(OrderStates, next_field_config["state_name"]))
    await state.update_data(current_field_key=next_field_config["key"])  # Обновляем текущий ключ поля

    prompt_text = get_localized_message(next_field_config["prompt_key"], lang)

    logger.info(f"Пользователь {user_id}: Запрашиваем поле '{next_field_key}' с типом ввода '{next_field_config['input_type']}'.") # Добавлено логирование

    # Логика отправки сообщения в зависимости от типа ввода и типа update_object
    if next_field_config["input_type"] == "buttons":  # InlineKeyboardMarkup
        keyboard = InlineKeyboardBuilder()
        for option_key, option_value in next_field_config["options_keys"].items():
            keyboard.button(text=get_localized_message(option_key, lang),
                            callback_data=f"set_field_{next_field_key}_{option_value}")
        keyboard.adjust(1)
        reply_markup_to_send = keyboard.as_markup()

        if isinstance(update_object, CallbackQuery):
            await update_object.message.edit_text(prompt_text, reply_markup=reply_markup_to_send,
                                                  parse_mode=ParseMode.HTML)
            await update_object.answer()
        elif isinstance(update_object, Message):
            await update_object.answer(prompt_text, reply_markup=reply_markup_to_send, parse_mode=ParseMode.HTML)

    elif next_field_config["input_type"] == "contact_button":  # ReplyKeyboardMarkup
        reply_markup_to_send = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_localized_message("button_send_phone_number", lang), request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        # Для ReplyKeyboardMarkup всегда отправляем новое сообщение.
        # Если предыдущее действие было CallbackQuery, удаляем старое сообщение.
        if isinstance(update_object, CallbackQuery):
            await update_object.message.delete()  # Удаляем сообщение с инлайн-клавиатурой
            await update_object.message.answer(prompt_text, reply_markup=reply_markup_to_send,
                                               parse_mode=ParseMode.HTML)
            await update_object.answer()  # Отвечаем на callback, чтобы убрать "часики"
        elif isinstance(update_object, Message):
            await update_object.answer(prompt_text, reply_markup=reply_markup_to_send, parse_mode=ParseMode.HTML)

    elif next_field_config["input_type"] == "text": # Обработка текстового ввода
        reply_markup_to_send = ReplyKeyboardRemove() # Удаляем предыдущую ReplyKeyboardMarkup, если она была

        # ИСПРАВЛЕНО: Если предыдущее действие было CallbackQuery, удаляем старое сообщение
        # и отправляем новое с ReplyKeyboardRemove.
        if isinstance(update_object, CallbackQuery):
            await update_object.message.delete() # Удаляем сообщение с инлайн-клавиатурой
            await update_object.message.answer(prompt_text, reply_markup=reply_markup_to_send, parse_mode=ParseMode.HTML)
            await update_object.answer()
        elif isinstance(update_object, Message):
            # Если предыдущее сообщение было обычным текстом, отвечаем новым сообщением
            await update_object.answer(prompt_text, reply_markup=reply_markup_to_send, parse_mode=ParseMode.HTML)
    else:
        logger.error(f"Пользователь {user_id}: Неизвестный тип ввода '{next_field_config['input_type']}' для поля '{next_field_key}'. Возврат в главное меню.") # Добавлено логирование
        # Обработка ошибки: возвращение в главное меню
        if isinstance(update_object, CallbackQuery):
            await update_object.answer(get_localized_message("error_input_type", lang), show_alert=True)
            await _display_user_main_menu(update_object, state, lang=lang)
        elif isinstance(update_object, Message):
            await update_object.answer(get_localized_message("error_input_type", lang))
            await _display_user_main_menu(update_object, state, lang=lang)


# --- Хэндлеры для каждого поля заказа ---

@router.message(OrderStates.waiting_for_order_text)
async def process_order_text(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает ввод текста заказа.
    """
    user_id = message.from_user.id
    order_text = message.text.strip()
    logger.info(f"Пользователь {user_id} ввел текст заказа.")

    if not order_text:
        await message.answer(get_localized_message("prompt_order_text", lang), parse_mode=ParseMode.HTML)
        return

    await state.update_data(order_text=order_text)

    keyboard = InlineKeyboardBuilder()
    # Callback data теперь указывает на подтверждение конкретного поля
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang),
                                      callback_data="confirm_field_input:order_text"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    reply_markup = keyboard.as_markup()

    confirmation_text = get_localized_message("prompt_order_text_confirmation", lang).format(
        order_text=html.escape(order_text))

    await message.answer(confirmation_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@router.message(OrderStates.waiting_for_full_name)
async def process_full_name(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает ввод полного имени.
    """
    user_id = message.from_user.id
    full_name = message.text.strip()
    logger.info(f"Пользователь {user_id} ввел полное имя.")

    if not full_name:
        await message.answer(get_localized_message("prompt_full_name", lang), parse_mode=ParseMode.HTML)
        return

    await state.update_data(full_name=full_name)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang),
                                      callback_data="confirm_field_input:full_name"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    reply_markup = keyboard.as_markup()

    confirmation_text = get_localized_message("prompt_full_name_confirmation", lang).format(
        full_name=html.escape(full_name))

    await message.answer(confirmation_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@router.message(OrderStates.waiting_for_delivery_address)
async def process_delivery_address(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает ввод адреса доставки.
    """
    user_id = message.from_user.id
    delivery_address = message.text.strip()
    logger.info(f"Пользователь {user_id} ввел адрес доставки.")

    if not delivery_address:
        await message.answer(get_localized_message("prompt_delivery_address", lang), parse_mode=ParseMode.HTML)
        return

    await state.update_data(delivery_address=delivery_address)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang),
                                      callback_data="confirm_field_input:delivery_address"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    reply_markup = keyboard.as_markup()

    confirmation_text = get_localized_message("prompt_delivery_address_confirmation", lang).format(
        delivery_address=html.escape(delivery_address))

    await message.answer(confirmation_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("set_field_payment_method_"))
async def process_payment_method(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает выбор метода оплаты через инлайн-кнопки.
    """
    user_id = callback.from_user.id
    payment_method = callback.data.split("_")[-1]  # Получаем значение из callback_data
    logger.info(f"Пользователь {user_id} выбрал метод оплаты: {payment_method}.")

    await state.update_data(payment_method=payment_method)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang),
                                      callback_data="confirm_field_input:payment_method"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    reply_markup = keyboard.as_markup()

    # Получаем локализованное название метода оплаты для подтверждения
    payment_options = ORDER_FIELD_MAP.get("payment_method", {}).get("options_keys", {})
    localized_payment_method_key = next((k for k, v in payment_options.items() if v == payment_method), None)
    display_payment_method = get_localized_message(localized_payment_method_key,
                                                   lang) if localized_payment_method_key else payment_method

    confirmation_text = get_localized_message("prompt_payment_method_confirmation", lang).format(
        payment_method=html.escape(display_payment_method))

    await callback.message.edit_text(confirmation_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(OrderStates.waiting_for_contact_phone)
async def process_contact_phone(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает ввод или отправку контактного телефона.
    """
    user_id = message.from_user.id
    contact_phone = None

    if message.contact:
        contact_phone = message.contact.phone_number
        logger.info(f"Пользователь {user_id} отправил контактный телефон через кнопку: {contact_phone}.")
        # Удаляем клавиатуру с кнопкой "Отправить номер телефона"
        await message.answer(get_localized_message("thank_you_processing", lang), reply_markup=ReplyKeyboardRemove())
    elif message.text:
        text_input = message.text.strip()
        if PHONE_NUMBER_REGEX.fullmatch(text_input):
            contact_phone = text_input
            logger.info(f"Пользователь {user_id} ввел контактный телефон: {contact_phone}.")
        else:
            await message.answer(get_localized_message("error_invalid_phone_format", lang), parse_mode=ParseMode.HTML)
            return

    if not contact_phone:
        await message.answer(get_localized_message("prompt_contact_phone", lang), parse_mode=ParseMode.HTML)
        return

    await state.update_data(contact_phone=contact_phone)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang),
                                      callback_data="confirm_field_input:contact_phone"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    reply_markup = keyboard.as_markup()

    confirmation_text = get_localized_message("prompt_contact_phone_confirmation", lang).format(
        phone_number=html.escape(contact_phone))

    await message.answer(confirmation_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@router.message(OrderStates.waiting_for_delivery_notes)
async def process_delivery_notes(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает ввод примечаний к доставке.
    """
    user_id = message.from_user.id
    delivery_notes = message.text.strip()
    logger.info(f"Пользователь {user_id} ввел примечания к доставке.")

    # Если пользователь ввел "-", "нет" или что-то подобное, сохраняем это как пустую строку или специальное значение
    if delivery_notes.lower() in ["-", get_localized_message("no_notes_keyword", lang).lower()]:
        delivery_notes = get_localized_message("no_notes_display", lang)

    await state.update_data(delivery_notes=delivery_notes)

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang),
                                      callback_data="confirm_field_input:delivery_notes"))
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    reply_markup = keyboard.as_markup()

    confirmation_text = get_localized_message("prompt_delivery_notes_confirmation", lang).format(
        delivery_notes=html.escape(delivery_notes))

    await message.answer(confirmation_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


@router.callback_query(
    F.data.startswith("confirm_field_input:"))  # Изменено для обработки подтверждения конкретного поля
async def confirm_field_input(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает подтверждение текущего поля заказа.
    Переходит к следующему полю или к окончательному подтверждению.
    """
    user_id = callback.from_user.id
    confirmed_field_key = callback.data.split(":")[1]  # Извлекаем ключ подтвержденного поля
    logger.info(f"Пользователь {user_id} подтвердил поле: {confirmed_field_key}.")

    # Удаляем клавиатуру подтверждения
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(get_localized_message("thank_you_processing", lang))

    # Находим конфигурацию подтвержденного поля, чтобы определить следующее
    confirmed_field_config = ORDER_FIELD_MAP.get(confirmed_field_key)
    if not confirmed_field_config:
        logger.error(f"Не найдена конфигурация для подтвержденного поля: {confirmed_field_key}")
        await _display_user_main_menu(callback, state, lang=lang)
        return

    next_field_key = confirmed_field_config.get("next_field")

    # Вызываем _request_next_field с ключом следующего поля
    await _request_next_field(callback, state, lang=lang, next_field_key=next_field_key)


@router.callback_query(F.data == "final_confirm_order")
async def final_confirm_order(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        lang: str
):
    """
    Обрабатывает окончательное подтверждение заказа пользователем.
    Сохраняет заказ в базу данных, отправляет уведомление админам и очищает состояние.
    """
    user_data = await state.get_data()
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} окончательно подтвердил заказ.")

    # Получаем актуальные данные пользователя для username и т.д.
    user = await get_or_create_user(
        user_id=user_id,
        username=callback.from_user.username, # Передаем username из callback
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name
    )
    username_to_save = user.username if user else None

    new_order = await add_new_order(
        user_id=user_id,
        username=username_to_save,
        order_text=user_data.get('order_text', get_localized_message("not_specified", lang)),
        full_name=user_data.get('full_name'),
        delivery_address=user_data.get('delivery_address'),
        payment_method=user_data.get('payment_method'),
        contact_phone=user_data.get('contact_phone'),
        delivery_notes=user_data.get('delivery_notes', get_localized_message("no_notes_display", lang))
    )

    if new_order:
        await callback.message.edit_text(
            get_localized_message("order_placed_success", lang).format(order_id=new_order.id),
            parse_mode=ParseMode.HTML
        )
        # ИЗМЕНЕНО: Теперь передаем только ID заказа
        await send_new_order_notification_to_admins(bot, new_order.id)
        # Отправляем уведомление пользователю (если уведомления включены)
        await send_user_notification(
            bot,
            user_id,
            "order_placed_success_user_notification", # Новый ключ локализации для уведомления пользователя
            lang,
            order_id=new_order.id
        )
    else:
        await callback.message.edit_text(
            get_localized_message("error_order_processing", lang),
            parse_mode=ParseMode.HTML
        )

    await state.clear()
    # Возвращаемся в главное меню после оформления заказа
    await _display_user_main_menu(callback, state, lang=lang)
    await callback.answer()


@router.callback_query(F.data == "cancel_order")
async def cancel_order(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает отмену заказа пользователем на любом этапе.
    Очищает FSM-состояние и возвращает пользователя в главное меню.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} отменил заказ.")

    await state.clear()
    await callback.message.edit_text(get_localized_message("order_cancelled_success", lang))
    # Возвращаемся в главное меню после отмены
    await _display_user_main_menu(callback, state, lang=lang)
    await callback.answer()
