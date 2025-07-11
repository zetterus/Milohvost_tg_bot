import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from .admin_utils import _display_admin_main_menu
from .admin_filters import IsAdmin
from db import get_or_create_user

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("admin"), IsAdmin())
async def admin_command(
        message: Message,
        state: FSMContext,
        # storage: BaseStorage, # <-- УДАЛЕНО
        # storage_key: StorageKey, # <-- УДАЛЕНО
        lang: str
):
    """
    Обрабатывает команду /admin.
    Проверяет админ-права и отображает главное меню админ-панели.
    Эта команда всегда возвращает админа в начальное состояние админ-панели.
    Обновляет данные пользователя и его активность в БД.
    """
    logger.info(f"Админ {message.from_user.id} вызвал команду /admin.")

    await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    await _display_admin_main_menu(message, state, lang=lang)


@router.callback_query(F.data == "admin_panel_back", IsAdmin())
async def admin_panel_callbacks(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает callback-запросы для возврата в главное меню админ-панели из подменю.
    Обновляет активность пользователя в БД.
    """
    logger.info(f"Админ {callback.from_user.id} вернулся в главное меню админ-панели.")

    await get_or_create_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name
    )

    await _display_admin_main_menu(callback, state, lang=lang)
