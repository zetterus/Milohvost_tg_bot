import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton

from db import get_active_help_message_from_db
from .user_utils import _display_user_main_menu # Импортируем функцию для возврата в главное меню

logger = logging.getLogger(__name__)
router = Router() # Локальный роутер для этого модуля

@router.callback_query(F.data == "get_help")
async def get_help_callback(callback: CallbackQuery):
    """
    Обрабатывает нажатие инлайн-кнопки "Помощь".
    Отправляет пользователю заранее заданное сообщение помощи.
    """
    logger.info(f"Пользователь {callback.from_user.id} запросил помощь.")

    active_message = await get_active_help_message_from_db()

    text_to_send = ""
    if active_message:
        text_to_send = active_message.message_text
    else:
        text_to_send = "Извини, сообщение помощи пока не настроено."

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🔙 В главное меню", callback_data="user_main_menu_back"))

    await callback.message.edit_text(text_to_send, reply_markup=keyboard.as_markup(), parse_mode="Markdown")
    await callback.answer()
