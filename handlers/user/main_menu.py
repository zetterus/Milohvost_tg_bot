import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from db import get_or_create_user
from .user_utils import _display_user_main_menu

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def start_command(
        message: Message,
        state: FSMContext,
        lang: str # <-- ОСТАВЛЕНО: Язык будет инжектирован LocalizationMiddleware
):
    """
    Обрабатывает команду /start.
    Отправляет приветственное сообщение и главное меню с инлайн-кнопками,
    сбрасывая FSM-состояние пользователя.
    Обновляет данные пользователя и его активность в БД.
    """
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}")

    await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    await state.clear() # Очищаем FSM-состояние

    # Вызываем функцию отображения меню, передавая lang
    await _display_user_main_menu(message, state, lang=lang)


@router.callback_query(F.data == "user_main_menu_back")
async def user_main_menu_back_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str # <-- ОСТАВЛЕНО: Язык будет инжектирован LocalizationMiddleware
):
    """
    Обрабатывает возврат пользователя в главное меню из любого подменю.
    Редактирует текущее сообщение, отображая главное меню пользователя,
    и сбрасывает FSM-состояние.
    Обновляет активность пользователя в БД.
    """
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню.")

    await get_or_create_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name
    )

    await state.clear() # Очищаем FSM-состояние

    # Вызываем функцию отображения меню, передавая lang
    await _display_user_main_menu(callback, state, lang=lang)
