import logging
# from typing import Dict, Any # <-- УДАЛЕНО: Dict и Any больше не нужны

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
# from aiogram.fsm.storage.base import BaseStorage, StorageKey # <-- УДАЛЕНО: Больше не нужны здесь

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

    # get_or_create_user теперь не требует storage_key и storage_obj
    await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )

    # Вызываем функцию отображения меню, передавая lang
    await _display_admin_main_menu(message, state, lang=lang) # <-- ИЗМЕНЕНО: Передаем lang


@router.callback_query(F.data == "admin_panel_back", IsAdmin())
async def admin_panel_callbacks(
        callback: CallbackQuery,
        state: FSMContext,
        # storage: BaseStorage, # <-- УДАЛЕНО
        # storage_key: StorageKey, # <-- УДАЛЕНО
        lang: str
):
    """
    Обрабатывает callback-запросы для возврата в главное меню админ-панели из подменю.
    Обновляет активность пользователя в БД.
    """
    logger.info(f"Админ {callback.from_user.id} вернулся в главное меню админ-панели.")

    # get_or_create_user теперь не требует storage_key и storage_obj
    await get_or_create_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name
    )

    # Вызываем функцию отображения меню, передавая lang
    await _display_admin_main_menu(callback, state, lang=lang) # <-- ИЗМЕНЕНО: Передаем lang
