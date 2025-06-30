import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from db import add_new_order
from config import DISPLAY_FIELD_NAMES

# Импортируем OrderStates из общего __init__.py пакета user
from .user_states import OrderStates
from .user_utils import _display_user_main_menu # Для отмены заказа

logger = logging.getLogger(__name__)
router = Router() # Локальный роутер для этого модуля

# Обработчики для создания заказа
@router.callback_query(F.data == "make_order")
async def make_order_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие инлайн-кнопки "Сделать заказ".
    Переводит пользователя в состояние ожидания текста заказа.
    """
    logger.info(f"Пользователь {callback.from_user.id} нажал 'Сделать заказ'")
    await callback.message.edit_text("Введите заказ: 📝")
    await state.set_state(OrderStates.waiting_for_order_text)
    await callback.answer()

@router.message(OrderStates.waiting_for_order_text)
async def process_order_text(message: Message, state: FSMContext):
    """
    Обрабатывает ввод пользователем основного текста заказа.
    Предлагает подтвердить или отменить.
    """
    logger.info(f"Пользователь {message.from_user.id} ввел текст заказа.")
    await state.update_data(order_text=message.text)

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Подтвердить ✅", callback_data="confirm_input:full_name")
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
    elif field_to_ask == "final_confirm":
        await _show_order_summary(callback.message, state)

    await callback.answer()

@router.message(OrderStates.waiting_for_full_name)
@router.message(OrderStates.waiting_for_delivery_address)
@router.message(OrderStates.waiting_for_contact_phone)
@router.message(OrderStates.waiting_for_delivery_notes)
async def process_order_field(message: Message, state: FSMContext):
    """
    Общий обработчик для полей заказа (ФИО, адрес, телефон, примечания).
    Сохраняет введенные данные и предлагает подтвердить или отменить.
    """
    current_state_str = await state.get_state()

    field_mapping = {
        'OrderStates:waiting_for_full_name': 'full_name',
        'OrderStates:waiting_for_delivery_address': 'delivery_address',
        'OrderStates:waiting_for_contact_phone': 'contact_phone',
        'OrderStates:waiting_for_delivery_notes': 'delivery_notes',
    }

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

    next_field_logic = {
        "waiting_for_full_name": "delivery_address",
        "waiting_for_delivery_address": "payment_method",
        "waiting_for_contact_phone": "delivery_notes",
        "waiting_for_delivery_notes": "final_confirm"
    }

    current_step_name = current_state_str.split(':')[-1]
    next_field = next_field_logic.get(current_step_name)

    keyboard = InlineKeyboardBuilder()
    if next_field:
        keyboard.button(text="Подтвердить ✅", callback_data=f"confirm_input:{next_field}")
    else:
        keyboard.button(text="Подтвердить ✅", callback_data="confirm_input:final_confirm")

    keyboard.button(text="Отменить ❌", callback_data="cancel_order")
    keyboard.adjust(2)

    display_field_name = DISPLAY_FIELD_NAMES.get(field_to_save, field_to_save.replace('_', ' '))

    await message.answer(
        f"*{display_field_name.capitalize()}*: *{message.text}*\n\nВсё верно?",
        reply_markup=keyboard.as_markup(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("set_payment_method:"))
async def set_payment_method(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает выбор способа оплаты с помощью инлайн-кнопок.
    Сохраняет выбранный способ и переходит к запросу контактного телефона.
    """
    payment_method = callback.data.split(":")[1]
    await state.update_data(payment_method=payment_method)
    logger.info(f"Пользователь {callback.from_user.id} выбрал способ оплаты: {payment_method}")

    await callback.message.edit_text(
        f"Ты выбрал способ оплаты: *{payment_method}*.\n\nТеперь введи свой **контактный телефон** 📞:",
        parse_mode="Markdown")
    await state.set_state(OrderStates.waiting_for_contact_phone)
    await callback.answer()

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает отмену заказа на любом этапе.
    Сбрасывает состояние и очищает данные.
    """
    logger.info(f"Пользователь {callback.from_user.id} отменил заказ.")
    await state.clear()
    await _display_user_main_menu(callback, state)
    await callback.answer()

async def _show_order_summary(message: Message, state: FSMContext):
    """
    Показывает пользователю полную сводку заказа для окончательного подтверждения.
    """
    user_data = await state.get_data()

    order_summary_parts = []
    for key, display_name in DISPLAY_FIELD_NAMES.items():
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
    Обрабатывает окончательное подтверждение заказа пользователем.
    Сохраняет заказ в базу данных и очищает состояние.
    """
    user_data = await state.get_data()
    logger.info(f"Пользователь {callback.from_user.id} окончательно подтвердил заказ.")

    new_order = await add_new_order(
        user_id=callback.from_user.id,
        username=callback.from_user.username or callback.from_user.full_name,
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
