import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from .user_utils import _display_user_main_menu

logger = logging.getLogger(__name__)
router = Router()  # Локальный роутер для этого модуля


@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    """
    Обрабатывает команду /start.
    Отправляет приветственное сообщение и главное меню с инлайн-кнопками.
    """
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}")
    await _display_user_main_menu(message, state)


@router.callback_query(F.data == "user_main_menu_back")
async def user_main_menu_back_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает возврат пользователя в главное меню из любой точки.
    """
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню.")
    await _display_user_main_menu(callback, state)
