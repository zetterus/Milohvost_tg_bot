import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage, StorageKey # <-- НОВЫЙ ИМПОРТ

from db import get_active_help_message_from_db
from localization import get_localized_message # <-- НОВЫЙ ИМПОРТ

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "get_help")
async def get_help_callback(
    callback: CallbackQuery,
    storage: BaseStorage, # <-- ДОБАВЛЕНО: получаем объект хранилища
    storage_key: StorageKey # <-- ДОБАВЛЕНО: получаем StorageKey
):
    """
    Обрабатывает нажатие инлайн-кнопки "Помощь".
    Отправляет пользователю заранее заданное сообщение помощи, используя локализацию.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил помощь.")

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk') # По умолчанию 'uk'

    active_message = await get_active_help_message_from_db()

    # Определяем текст для отправки в зависимости от наличия активного сообщения
    # Используем локализованное сообщение, если активное сообщение не настроено
    text_to_send = active_message.message_text if active_message else \
                   get_localized_message("help_message_not_configured", lang)

    keyboard = InlineKeyboardBuilder()
    # Локализуем текст кнопки "В главное меню"
    keyboard.row(InlineKeyboardButton(
        text=get_localized_message("button_back_to_main_menu", lang),
        callback_data="user_main_menu_back"
    ))

    await callback.message.edit_text(text_to_send, reply_markup=keyboard.as_markup(), parse_mode=ParseMode.HTML)
    await callback.answer()

