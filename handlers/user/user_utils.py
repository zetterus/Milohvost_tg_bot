import logging
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
router = Router()


async def _display_user_main_menu(update_object: Message | CallbackQuery, state: FSMContext):
    """
    Отображает главное меню для пользователя.
    :param update_object: Объект Message или CallbackQuery, инициировавший отображение.
    """

    await state.clear()  # Очищаем все данные из FSM, чтобы начать с чистого листа

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="Сделать заказ 📝", callback_data="make_order")
    keyboard.button(text="Посмотреть мои заказы 📦", callback_data="view_my_orders")
    keyboard.button(text="Помощь ❓", callback_data="get_help")
    keyboard.adjust(1)

    menu_text = "Привет! Я бот для оформления заказов. Что ты хочешь сделать?"

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=keyboard.as_markup())
    elif isinstance(update_object, CallbackQuery):
        await update_object.message.edit_text(menu_text, reply_markup=keyboard.as_markup())
        await update_object.answer()  # Закрываем уведомление о нажатии кнопки
