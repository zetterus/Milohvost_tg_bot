import logging
import re
from typing import Union
import html

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
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage, StorageKey  # <-- НОВЫЙ ИМПОРТ

from db import add_new_order
from config import (
    ORDER_FIELDS_CONFIG,  # DISPLAY_FIELD_NAMES больше не используется напрямую для текстов
    ORDER_FIELD_MAP,
    PHONE_NUMBER_REGEX,
    ORDER_FIELD_NAMES_KEYS  # <-- НОВЫЙ ИМПОРТ: для локализации названий полей
)
from .user_states import OrderStates
from .user_utils import _display_user_main_menu
from localization import get_localized_message  # <-- НОВЫЙ ИМПОРТ

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "make_order")
async def make_order_callback(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает нажатие инлайн-кнопки "Сделать заказ".
    Начинает процесс оформления заказа, запрашивая первое поле из конфигурации.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} нажал 'Сделать заказ'.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    # Получаем конфигурацию для первого поля (order_text)
    first_field_config = ORDER_FIELDS_CONFIG[0]

    # Используем prompt_key для получения локализованного текста запроса
    prompt_text = get_localized_message(first_field_config["prompt_key"], lang)

    await callback.message.edit_text(prompt_text, parse_mode=ParseMode.HTML)
    # Устанавливаем состояние, используя getattr для получения объекта состояния по имени
    await state.set_state(getattr(OrderStates, first_field_config["state_name"]))
    await callback.answer()


@router.message(OrderStates.waiting_for_order_text)
async def process_order_text(
        message: Message,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает ввод пользователя для основного текста заказа.
    Предлагает подтверждение или отмену, переходя к следующему полю (full_name).
    """
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} ввел текст заказа.")
    await state.update_data(order_text=message.text)

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    current_field_config = ORDER_FIELD_MAP.get("order_text")
    if not current_field_config:
        logger.error(f"Конфигурация для 'order_text' не найдена для пользователя {user_id}.")
        await message.answer(
            get_localized_message("error_order_processing", lang),  # <-- Локализовано
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return

    next_field_key = current_field_config.get("next_field")
    if not next_field_key:
        logger.error(f"Следующее поле для 'order_text' не определено в конфиге для пользователя {user_id}.")
        await message.answer(
            get_localized_message("error_order_processing", lang),  # <-- Локализовано
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_confirm", lang),
                    callback_data=f"confirm_input:{next_field_key}")  # <-- Локализовано
    keyboard.button(text=get_localized_message("button_cancel", lang), callback_data="cancel_order")  # <-- Локализовано
    keyboard.adjust(2)

    escaped_text = html.escape(message.text)
    # Используем локализованное сообщение для подтверждения текста заказа
    confirm_message = get_localized_message("prompt_order_text_confirmation", lang).format(
        order_text=f"<b>{escaped_text}</b>")
    await message.answer(
        confirm_message,  # <-- Локализовано
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data.startswith("confirm_input:"))
async def confirm_input_and_next(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает подтверждение ввода предыдущего поля и запрашивает следующее поле.
    Использует ORDER_FIELD_MAP для динамической генерации запроса.
    """
    user_id = callback.from_user.id
    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    # Извлекаем ключ следующего поля из callback_data. Пример: "confirm_input:full_name"
    field_to_ask_key = callback.data.split(":")[1]
    user_data = await state.get_data()
    logger.info(
        f"Пользователь {user_id} подтвердил ввод. Запрашивается: {field_to_ask_key}. Данные: {user_data}")

    # Если это окончательное подтверждение перед показом сводки
    if field_to_ask_key == "final_confirm":
        # Передаем storage и storage_key в _show_order_summary
        await _show_order_summary(callback.message, state, storage=storage, storage_key=storage_key)  # <-- ДОБАВЛЕНО
        await callback.answer()
        return

    next_field_config = ORDER_FIELD_MAP.get(field_to_ask_key)

    if not next_field_config:
        logger.error(f"Конфигурация для поля '{field_to_ask_key}' не найдена для пользователя {user_id}.")
        await callback.message.edit_text(
            get_localized_message("error_order_processing", lang),  # <-- Локализовано
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        await callback.answer()
        return

    input_type = next_field_config.get("input_type")
    # Используем prompt_key для получения локализованного текста запроса
    prompt_text = get_localized_message(next_field_config["prompt_key"], lang)  # <-- Локализовано
    state_to_set = getattr(OrderStates, next_field_config["state_name"])

    if input_type == "text":
        await callback.message.edit_text(prompt_text, parse_mode=ParseMode.HTML)
        await state.set_state(state_to_set)
    elif input_type == "buttons":
        keyboard = InlineKeyboardBuilder()
        # Итерируемся по options_keys для получения локализованных текстов кнопок
        for button_key, data_value in next_field_config[
            "options_keys"].items():  # <-- ИСПРАВЛЕНО: options на options_keys
            keyboard.button(text=get_localized_message(button_key, lang),
                            callback_data=f"set_{field_to_ask_key}:{data_value}")  # <-- Локализовано
        keyboard.adjust(1)
        await callback.message.edit_text(
            prompt_text,
            reply_markup=keyboard.as_markup(),
            parse_mode=ParseMode.HTML
        )
        await state.set_state(state_to_set)
    elif input_type == "contact_button":
        reply_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=get_localized_message("button_send_phone_number", lang), request_contact=True)]
                # <-- Локализовано
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await callback.message.delete()
        await callback.message.answer(
            prompt_text,
            reply_markup=reply_keyboard,
            parse_mode=ParseMode.HTML
        )
        await state.set_state(state_to_set)
    else:
        logger.error(f"Неизвестный тип ввода '{input_type}' для поля '{field_to_ask_key}' для пользователя {user_id}.")
        await callback.message.edit_text(
            get_localized_message("error_input_type", lang),  # <-- Локализовано
            parse_mode=ParseMode.HTML
        )
        await state.clear()

    await callback.answer()


@router.message(OrderStates.waiting_for_full_name)
async def process_full_name_input(
        message: Message,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает ввод пользователя для полного имени.
    Сохраняет данные, предлагает подтверждение и переходит к следующему шагу.
    """
    user_id = message.from_user.id
    await state.update_data(full_name=message.text)
    logger.info(f"Пользователь {user_id} ввел полное имя: {message.text}")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    current_field_config = ORDER_FIELD_MAP.get("full_name")
    next_field_key = current_field_config.get("next_field")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_confirm", lang),
                    callback_data=f"confirm_input:{next_field_key}")  # <-- Локализовано
    keyboard.button(text=get_localized_message("button_cancel", lang), callback_data="cancel_order")  # <-- Локализовано
    keyboard.adjust(2)

    # Получаем локализованное название поля
    display_field_name_key = ORDER_FIELD_NAMES_KEYS.get("full_name")
    display_field_name = get_localized_message(display_field_name_key, lang)  # <-- Локализовано

    escaped_text = html.escape(message.text)
    # Используем локализованное сообщение для подтверждения
    confirm_message = get_localized_message("prompt_full_name_confirmation", lang).format(
        full_name=f"<b>{escaped_text}</b>"
    )
    await message.answer(
        confirm_message,  # <-- Локализовано
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.message(OrderStates.waiting_for_delivery_address)
async def process_delivery_address_input(
        message: Message,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает ввод пользователя для адреса доставки.
    Сохраняет данные, предлагает подтверждение и переходит к следующему шагу.
    """
    user_id = message.from_user.id
    await state.update_data(delivery_address=message.text)
    logger.info(f"Пользователь {user_id} ввел адрес доставки: {message.text}")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    current_field_config = ORDER_FIELD_MAP.get("delivery_address")
    next_field_key = current_field_config.get("next_field")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_confirm", lang),
                    callback_data=f"confirm_input:{next_field_key}")  # <-- Локализовано
    keyboard.button(text=get_localized_message("button_cancel", lang), callback_data="cancel_order")  # <-- Локализовано
    keyboard.adjust(2)

    # Получаем локализованное название поля
    display_field_name_key = ORDER_FIELD_NAMES_KEYS.get("delivery_address")
    display_field_name = get_localized_message(display_field_name_key, lang)  # <-- Локализовано

    escaped_text = html.escape(message.text)
    # Используем локализованное сообщение для подтверждения
    confirm_message = get_localized_message("prompt_delivery_address_confirmation", lang).format(
        delivery_address=f"<b>{escaped_text}</b>"
    )
    await message.answer(
        confirm_message,  # <-- Локализовано
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.message(OrderStates.waiting_for_delivery_notes)
async def process_delivery_notes_input(
        message: Message,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает ввод пользователя для примечаний к доставке.
    Сохраняет данные, предлагает подтверждение и переходит к следующему шагу (окончательное подтверждение).
    """
    user_id = message.from_user.id
    await state.update_data(delivery_notes=message.text)
    logger.info(f"Пользователь {user_id} ввел примечания к доставке: {message.text}")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    current_field_config = ORDER_FIELD_MAP.get("delivery_notes")
    next_field_key = current_field_config.get("next_field")  # Ожидается "final_confirm"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_confirm", lang),
                    callback_data=f"confirm_input:{next_field_key}")  # <-- Локализовано
    keyboard.button(text=get_localized_message("button_cancel", lang), callback_data="cancel_order")  # <-- Локализовано
    keyboard.adjust(2)

    # Получаем локализованное название поля
    display_field_name_key = ORDER_FIELD_NAMES_KEYS.get("delivery_notes")
    display_field_name = get_localized_message(display_field_name_key, lang)  # <-- Локализовано

    escaped_text = html.escape(message.text)
    # Используем локализованное сообщение для подтверждения
    confirm_message = get_localized_message("prompt_delivery_notes_confirmation", lang).format(
        delivery_notes=f"<b>{escaped_text}</b>"
    )
    await message.answer(
        confirm_message,  # <-- Локализовано
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )


@router.message(OrderStates.waiting_for_contact_phone)
async def process_contact_phone(
        message: Message,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает ввод контактного телефона. Принимает как текстовый ввод, так и контакт через кнопку.
    Проверяет формат для ручного ввода.
    """
    user_id = message.from_user.id

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    contact_phone = None

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
            await message.answer(get_localized_message("thank_you_processing", lang),
                                 reply_markup=ReplyKeyboardRemove())  # <-- Локализовано
        else:
            # Неверный формат - остаемся в этом же состоянии
            await message.answer(
                get_localized_message("error_invalid_phone_format", lang),  # <-- Локализовано
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text=get_localized_message("button_send_phone_number", lang),
                                              request_contact=True)]],  # <-- Локализовано
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
        confirm_message_text = get_localized_message("prompt_contact_phone_confirmation", lang).format(
            phone_number=html.escape(contact_phone)
        )  # <-- Локализовано

        # Создаем Inline-клавиатуру для подтверждения
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text=get_localized_message("button_confirm", lang),
                        callback_data=f"confirm_input:{next_field_key}")  # <-- Локализовано
        keyboard.button(text=get_localized_message("button_cancel", lang),
                        callback_data="cancel_order")  # <-- Локализовано
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
async def set_payment_method(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает выбор метода оплаты с помощью инлайн-кнопок.
    Сохраняет выбранный метод и переходит к запросу контактного телефона.
    """
    user_id = callback.from_user.id
    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    payment_method_value = callback.data.split(":")[1]  # Получаем системное значение, например 'cash'
    await state.update_data(payment_method=payment_method_value)
    logger.info(f"Пользователь {user_id} выбрал метод оплаты: {payment_method_value}")

    # Получаем локализованное название выбранного метода оплаты для отображения
    # Итерируемся по options_keys, чтобы найти ключ локализации по системному значению
    payment_method_display_name = ""
    payment_field_config = ORDER_FIELD_MAP.get("payment_method")
    if payment_field_config and "options_keys" in payment_field_config:
        for button_key, value in payment_field_config["options_keys"].items():
            if value == payment_method_value:
                payment_method_display_name = get_localized_message(button_key, lang)
                break

    if not payment_method_display_name:
        payment_method_display_name = payment_method_value  # Fallback, если не найдено

    next_field_config_after_payment = ORDER_FIELD_MAP["payment_method"]
    next_field_key_after_payment = next_field_config_after_payment.get("next_field")
    contact_phone_config = ORDER_FIELD_MAP.get(next_field_key_after_payment)

    if not contact_phone_config:
        logger.error(
            f"Конфигурация для следующего поля '{next_field_key_after_payment}' не найдена после выбора метода оплаты для пользователя {user_id}.")
        await callback.message.edit_text(
            get_localized_message("error_order_processing", lang),  # <-- Локализовано
            parse_mode=ParseMode.HTML
        )
        await state.clear()
        await callback.answer()
        return

    reply_keyboard_for_phone = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=get_localized_message("button_send_phone_number", lang), request_contact=True)]
            # <-- Локализовано
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await callback.message.delete()  # Удаляем сообщение с выбором метода оплаты

    # Используем локализованное сообщение для подтверждения метода оплаты
    payment_confirmation_message = get_localized_message("prompt_payment_method_confirmation", lang).format(
        payment_method=f"<b>{html.escape(payment_method_display_name)}</b>"
    )  # <-- Локализовано

    # Используем prompt_key для получения локализованного текста запроса для следующего поля
    next_prompt_text = get_localized_message(contact_phone_config["prompt_key"], lang)  # <-- Локализовано

    await callback.message.answer(
        f"{payment_confirmation_message}\n\n{next_prompt_text}",  # Комбинируем сообщения
        reply_markup=reply_keyboard_for_phone,
        parse_mode=ParseMode.HTML
    )
    await state.set_state(getattr(OrderStates, contact_phone_config["state_name"]))
    await callback.answer()


@router.callback_query(F.data == "cancel_order")
async def cancel_order(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает отмену заказа на любой стадии.
    Сбрасывает состояние и очищает данные.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} отменил заказ.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    # Отправляем сообщение об отмене и пытаемся убрать Reply-клавиатуру, если она была активна
    await state.clear()
    await _display_user_main_menu(callback, state, storage=storage,
                                  storage_key=storage_key)  # <-- Передаем storage и storage_key
    await callback.message.answer(get_localized_message("order_cancelled_success", lang),
                                  parse_mode=ParseMode.HTML)  # <-- Локализовано
    await callback.answer()


async def _show_order_summary(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Показывает пользователю полную сводку заказа для окончательного подтверждения.
    Принимает Message или CallbackQuery и соответствующим образом отправляет/редактирует сообщение.
    Использует локализацию для названий полей и кнопок.
    """
    user_data = await state.get_data()
    user_id = update_object.from_user.id

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    order_summary_parts = []
    for field_config in ORDER_FIELDS_CONFIG:
        key = field_config["key"]

        # Получаем локализованное название поля из ORDER_FIELD_NAMES_KEYS
        display_name_key = ORDER_FIELD_NAMES_KEYS.get(key, key)  # Fallback на сам ключ
        display_name = get_localized_message(display_name_key, lang)

        value = user_data.get(key)

        # Специальная обработка для payment_method: получаем локализованное значение
        if key == "payment_method" and value:
            payment_method_display_name = ""
            payment_field_config = ORDER_FIELD_MAP.get("payment_method")
            if payment_field_config and "options_keys" in payment_field_config:
                for button_key, val in payment_field_config["options_keys"].items():
                    if val == value:
                        payment_method_display_name = get_localized_message(button_key, lang)
                        break
            value_to_display = payment_method_display_name if payment_method_display_name else value
        elif key == "delivery_notes" and (
                value is None or value.strip() == '-' or value.strip().lower() == get_localized_message(
                "no_notes_keyword", lang).lower()):  # <-- Локализовано "нет"
            value_to_display = get_localized_message("no_notes_display", lang)  # <-- Локализовано "Нет"
        else:
            value_to_display = value

        escaped_value = html.escape(str(value_to_display)) if value_to_display is not None else None

        if escaped_value:
            order_summary_parts.append(f"<b>{display_name.capitalize()}</b>: {escaped_value}")
        # Убрана отдельная ветка для delivery_notes, т.к. она теперь обрабатывается выше

    # Локализованный заголовок и подтверждение
    order_summary = get_localized_message("final_order_summary_title", lang) + "\n\n" + \
                    "\n".join(order_summary_parts) + "\n\n" + \
                    get_localized_message("final_order_summary_confirmation", lang)

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_confirm_and_send", lang),
                    callback_data="final_confirm_order")  # <-- Локализовано
    keyboard.button(text=get_localized_message("button_cancel_order", lang),
                    callback_data="cancel_order")  # <-- Локализовано
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
        await update_object.answer()


@router.callback_query(F.data == "final_confirm_order")
async def final_confirm_order(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,  # <-- ДОБАВЛЕНО
        storage_key: StorageKey  # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает окончательное подтверждение заказа пользователем.
    Сохраняет заказ в базу данных и очищает состояние.
    """
    user_data = await state.get_data()
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} окончательно подтвердил заказ.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')  # По умолчанию 'uk'

    # Используем username, если доступен, иначе полное имя, иначе ID пользователя
    username_to_save = callback.from_user.username or callback.from_user.full_name or str(user_id)

    # Локализация метода оплаты для сохранения в БД, если нужно (сейчас сохраняется системный ключ)
    # Если вы хотите сохранять локализованное название в БД, нужно изменить логику сохранения.
    # Сейчас сохраняется системное значение payment_method_value из callback.data.
    # Если нужно локализованное, то:
    # localized_payment_method = get_localized_message(payment_method_value_key, lang)
    # new_order = await add_new_order(..., payment_method=localized_payment_method, ...)

    new_order = await add_new_order(
        user_id=user_id,
        username=username_to_save,
        order_text=user_data.get('order_text', get_localized_message("not_specified_order_text", lang)),
        # <-- Локализовано
        full_name=user_data.get('full_name'),
        delivery_address=user_data.get('delivery_address'),
        payment_method=user_data.get('payment_method'),  # Здесь сохраняется системный ключ, как и раньше
        contact_phone=user_data.get('contact_phone'),
        delivery_notes=user_data.get('delivery_notes'),
    )

    # Локализованное сообщение об успешном оформлении заказа
    success_message = get_localized_message("order_placed_success", lang).format(
        order_id=new_order.id)  # <-- Локализовано

    await callback.message.edit_text(
        success_message,
        parse_mode=ParseMode.HTML
    )
    await state.clear()
    await callback.answer()

