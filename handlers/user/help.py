import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.enums import ParseMode

from db import get_active_help_message_from_db

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "get_help")
async def get_help_callback(callback: CallbackQuery):
    """
    Обрабатывает нажатие инлайн-кнопки "Помощь".
    Отправляет пользователю заранее заданное сообщение помощи.
    """
    logger.info(f"Пользователь {callback.from_user.id} запросил помощь.")

    active_message = await get_active_help_message_from_db()

    # Определяем текст для отправки в зависимости от наличия активного сообщения
    text_to_send = active_message.message_text if active_message else "Извини, сообщение помощи пока не настроено."

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🔙 В главное меню", callback_data="user_main_menu_back"))

    await callback.message.edit_text(text_to_send, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.HTML)
    await callback.answer()