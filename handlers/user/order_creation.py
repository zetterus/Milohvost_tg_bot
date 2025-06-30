import logging
import re

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

from db import add_new_order
from config import (
    DISPLAY_FIELD_NAMES,
    ORDER_FIELDS_CONFIG,
    ORDER_FIELD_MAP,
    PHONE_NUMBER_REGEX
)
from .user_states import OrderStates
from .main_menu import _display_user_main_menu


logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "make_order")
async def make_order_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие инлайн-кнопки "Сделать заказ".
    Начинает процесс оформления заказа, запрашивая первое поле из конфига.
    """
    logger.info(f"User {callback.from_user.id} pressed 'Make Order'.")

    # Get configuration for the first field (order_text)
    first_field_config = ORDER_FIELDS_CONFIG[0]

    await callback.message.edit_text(first_field_config["prompt"], parse_mode="Markdown")
    # Set the state using getattr to get the state object by name
    await state.set_state(getattr(OrderStates, first_field_config["state_name"]))
    await callback.answer()


@router.message(OrderStates.waiting_for_order_text)
async def process_order_text(message: Message, state: FSMContext):
    """
    Handles user input for the main order text.
    Suggests confirmation or cancellation, moving to the next field (full_name).
    """
    logger.info(f"User {message.from_user.id} entered order text.")
    await state.update_data(order_text=message.text)

    current_field_config = ORDER_FIELD_MAP.get("order_text")
    if not current_field_config:
        logger.error("Configuration for 'order_text' not found.")
        await message.answer("An error occurred during the order process. Please try again via /start.")
        await state.clear()
        return

    next_field_key = current_field_config.get("next_field")
    if not next_field_key:
        logger.error("Next field for 'order_text' is not defined in config.")
        await message.answer("An error occurred during the order process. Please try again via /start.")
        await state.clear()
        return

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    await message.answer(
        f"Твой заказ: *{message.text}*\n\nВсё верно? Подтверди, чтобы перейти к следующему шагу, или отмени заказ.",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data.startswith("confirm_input:"))
async def confirm_input_and_next(callback: CallbackQuery, state: FSMContext):
    """
    Handles confirmation of the previous field's input and requests the next field.
    Uses ORDER_FIELDS_CONFIG for dynamic prompt generation.
    """
    field_to_ask_key = callback.data.split(":")[1]
    user_data = await state.get_data()
    logger.info(f"User {callback.from_user.id} confirmed input. Requesting: {field_to_ask_key}. Data: {user_data}")

    if field_to_ask_key == "final_confirm":
        await _show_order_summary(callback.message, state)
        await callback.answer()
        return

    next_field_config = ORDER_FIELD_MAP.get(field_to_ask_key)

    if not next_field_config:
        logger.error(f"Configuration for field '{field_to_ask_key}' not found.")
        await callback.message.edit_text("An error occurred. Please try again via /start.")
        await state.clear()
        await callback.answer()
        return

    if next_field_config["input_type"] == "text":
        logger.debug(f"Setting state: {next_field_config['state_name']}")
        await callback.message.edit_text(next_field_config["prompt"], parse_mode="Markdown")
        await state.set_state(getattr(OrderStates, next_field_config["state_name"]))
    elif next_field_config["input_type"] == "buttons":
        keyboard = InlineKeyboardBuilder()
        for text, data_value in next_field_config["options"].items():
            keyboard.button(text=text, callback_data=f"set_{field_to_ask_key}:{data_value}")
        keyboard.adjust(1)
        await callback.message.edit_text(
            next_field_config["prompt"],
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )
        await state.set_state(getattr(OrderStates, next_field_config["state_name"]))
    elif next_field_config["input_type"] == "contact_button":
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await callback.message.delete()
        await callback.message.answer(
            next_field_config["prompt"],
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        await state.set_state(getattr(OrderStates, next_field_config["state_name"]))

    await callback.answer()


@router.message(OrderStates.waiting_for_full_name)
async def process_full_name_input(message: Message, state: FSMContext):
    """
    Handles user input for the full name.
    Saves the data, offers confirmation, and proceeds to the next step.
    """
    await state.update_data(full_name=message.text)
    logger.info(f"User {message.from_user.id} entered full name: {message.text}")

    current_field_config = ORDER_FIELD_MAP.get("full_name")
    next_field_key = current_field_config.get("next_field")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    display_field_name = DISPLAY_FIELD_NAMES.get("full_name", "Полное имя")

    await message.answer(
        f"*{display_field_name.capitalize()}*: *{message.text}*\n\nВсё верно?",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )


@router.message(OrderStates.waiting_for_delivery_address)
async def process_delivery_address_input(message: Message, state: FSMContext):
    """
    Handles user input for the delivery address.
    Saves the data, offers confirmation, and proceeds to the next step.
    """
    await state.update_data(delivery_address=message.text)
    logger.info(f"User {message.from_user.id} entered delivery address: {message.text}")

    current_field_config = ORDER_FIELD_MAP.get("delivery_address")
    next_field_key = current_field_config.get("next_field")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    display_field_name = DISPLAY_FIELD_NAMES.get("delivery_address", "Адрес доставки")

    await message.answer(
        f"*{display_field_name.capitalize()}*: *{message.text}*\n\nВсё верно?",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )


@router.message(OrderStates.waiting_for_delivery_notes)
async def process_delivery_notes_input(message: Message, state: FSMContext):
    """
    Handles user input for delivery notes.
    Saves the data, offers confirmation, and proceeds to the next step (final confirmation).
    """
    await state.update_data(delivery_notes=message.text)
    logger.info(f"User {message.from_user.id} entered delivery notes: {message.text}")

    current_field_config = ORDER_FIELD_MAP.get("delivery_notes")
    next_field_key = current_field_config.get("next_field")  # Expected to be "final_confirm"

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    display_field_name = DISPLAY_FIELD_NAMES.get("delivery_notes", "Примечания к доставке")

    await message.answer(
        f"*{display_field_name.capitalize()}*: *{message.text}*\n\nВсё верно?",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )


@router.message(OrderStates.waiting_for_contact_phone)
async def process_contact_phone(message: Message, state: FSMContext):
    """
    Handles contact phone input. Accepts both text and contact via button.
    Validates format for manual input.
    """
    contact_phone = None

    if message.contact:
        contact_phone = message.contact.phone_number
        logger.info(f"User {message.from_user.id} sent phone number via button: {contact_phone}")
    elif message.text:
        if re.fullmatch(PHONE_NUMBER_REGEX, message.text):
            contact_phone = message.text
            logger.info(f"User {message.from_user.id} entered phone number manually: {contact_phone}")
        else:
            await message.answer(
                ORDER_FIELD_MAP["contact_phone"]["prompt"],
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                ),
                parse_mode="Markdown"
            )
            return

    if contact_phone:
        await state.update_data(contact_phone=contact_phone)

        # Send a message to remove the Reply keyboard
        await message.answer(
            f"Твой контактный телефон: *{contact_phone}*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )

        # Then, in a SEPARATE message, offer confirmation
        next_field_config = ORDER_FIELD_MAP["contact_phone"]
        next_field_key = next_field_config.get("next_field")

        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field_key}")
        keyboard.button(text="Отменить ❌", callback_data="cancel_order")
        keyboard.adjust(2)

        await message.answer(
            "Всё верно? Подтверди, чтобы перейти к следующему шагу, или отмени заказ.",
            reply_markup=keyboard.as_markup(),
            parse_mode="Markdown"
        )
    else:
        # This block theoretically shouldn't be reached if `return` was triggered above
        await message.answer("Failed to get phone number. Please try again.")


@router.callback_query(F.data.startswith("set_payment_method:"))
async def set_payment_method(callback: CallbackQuery, state: FSMContext):
    """
    Handles payment method selection using inline buttons.
    Saves the selected method and proceeds to request the contact phone.
    """
    payment_method = callback.data.split(":")[1]
    await state.update_data(payment_method=payment_method)
    logger.info(f"User {callback.from_user.id} selected payment method: {payment_method}")

    next_field_config_after_payment = ORDER_FIELD_MAP["payment_method"]
    next_field_key_after_payment = next_field_config_after_payment.get("next_field")
    contact_phone_config = ORDER_FIELD_MAP.get(next_field_key_after_payment)

    if not contact_phone_config:
        logger.error(f"Configuration for the next field '{next_field_key_after_payment}' not found after payment.")
        await callback.message.edit_text("An error occurred. Please try again via /start.")
        await state.clear()
        await callback.answer()
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await callback.message.delete()
    await callback.message.answer(
        f"Ты выбрал способ оплаты: *{payment_method}*.\n\n" + contact_phone_config["prompt"],
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(getattr(OrderStates, contact_phone_config["state_name"]))
    await callback.answer()


@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    """
    Handles order cancellation at any stage.
    Resets the state and clears data.
    """
    logger.info(f"User {callback.from_user.id} canceled the order.")
    await callback.message.answer("Order canceled.", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    await _display_user_main_menu(callback, state)
    await callback.answer()


async def _show_order_summary(message: Message, state: FSMContext):
    """
    Shows the user the complete order summary for final confirmation.
    """
    user_data = await state.get_data()

    order_summary_parts = []
    for field_config in ORDER_FIELDS_CONFIG:
        key = field_config["key"]
        display_name = DISPLAY_FIELD_NAMES.get(key, key.replace('_', ' '))
        value = user_data.get(key)

        if value:
            order_summary_parts.append(f"*{display_name.capitalize()}*: {value}")
        elif key == 'delivery_notes':
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
    await state.set_state(OrderStates.confirm_order)


@router.callback_query(F.data == "final_confirm_order")
async def final_confirm_order(callback: CallbackQuery, state: FSMContext):
    """
    Handles the user's final order confirmation.
    Saves the order to the database and clears the state.
    """
    user_data = await state.get_data()
    logger.info(f"User {callback.from_user.id} finally confirmed the order.")

    username_to_save = callback.from_user.username or callback.from_user.full_name or str(callback.from_user.id)

    new_order = await add_new_order(
        user_id=callback.from_user.id,
        username=username_to_save,
        order_text=user_data.get('order_text', 'Не указан'),
        full_name=user_data.get('full_name'),
        delivery_address=user_data.get('delivery_address'),
        payment_method=user_data.get('payment_method'),
        contact_phone=user_data.get('contact_phone'),
        delivery_notes=user_data.get('delivery_notes'),
    )

    await callback.message.edit_text(
        f"✅ Твой заказ №*{new_order.id}* успешно оформлен! Мы свяжемся с тобой в ближайшее время.",
        parse_mode="Markdown"
    )
    await state.clear()
    await callback.answer()