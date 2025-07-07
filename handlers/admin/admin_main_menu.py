import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey # <-- НОВЫЙ ИМПОРТ

from .admin_utils import _display_admin_main_menu
from .admin_filters import IsAdmin

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("admin"), IsAdmin())
async def admin_command(
    message: Message,
    state: FSMContext,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО
    storage_key: StorageKey # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает команду /admin.
    Проверяет админ-права и отображает главное меню админ-панели.
    Эта команда всегда возвращает админа в начальное состояние админ-панели.
    """
    # Передаем storage и storage_key в _display_admin_main_menu
    await _display_admin_main_menu(message, state, storage=storage, storage_key=storage_key)


@router.callback_query(F.data == "admin_panel_back", IsAdmin())
async def admin_panel_callbacks(
    callback: CallbackQuery,
    state: FSMContext,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО
    storage_key: StorageKey # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает callback-запросы для возврата в главное меню админ-панели из подменю.
    """
    # Передаем storage и storage_key в _display_admin_main_menu
    await _display_admin_main_menu(callback, state, storage=storage, storage_key=storage_key)
