import logging
from typing import Union # Импортируем Union для type hinting

from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode # Явно импортируем ParseMode

logger = logging.getLogger(__name__)
router = Router()


async def _display_user_main_menu(update_object: Union[Message, CallbackQuery], state: FSMContext):
    """
    Отображает главное меню для пользователя, сбрасывая его FSM-состояние.
    Сообщение отправляется или редактируется в зависимости от типа объекта обновления.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение меню.
    :param state: FSMContext для управления состоянием пользователя.
    """
    user_id = update_object.from_user.id # Получаем ID пользователя для логирования
    logger.info(f"Пользователь {user_id} переходит в главное меню.")

    await state.clear()  # Очищаем все данные из FSM, чтобы начать с чистого листа

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Сделать заказ 📝", callback_data="make_order")
    keyboard.button(text="Посмотреть мои заказы 📦", callback_data="view_my_orders")
    keyboard.button(text="Помощь ❓", callback_data="get_help")
    keyboard.adjust(1) # Кнопки будут располагаться по одной в ряд

    menu_text = "Привет! Я бот для оформления заказов. Что ты хочешь сделать?"

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        # Отвечаем на CallbackQuery, чтобы убрать "часики"
        await update_object.answer()
        # Редактируем сообщение, так как оно уже существует
        await update_object.message.edit_text(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)