import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.storage.base import BaseStorage, StorageKey # Импорт BaseStorage и StorageKey

from db import get_or_create_user, get_user_language_code, update_user_language
from .user_utils import _display_user_main_menu # Импорт вспомогательной функции

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def start_command(
        message: Message,
        state: FSMContext,
        storage: BaseStorage,  # aiogram сам предоставит объект хранилища
        storage_key: StorageKey  # aiogram сам предоставит StorageKey
):
    """
    Обрабатывает команду /start.
    Отправляет приветственное сообщение и главное меню с инлайн-кнопками,
    сбрасывая FSM-состояние пользователя.
    Обновляет данные пользователя и его активность в БД и кэширует язык в Storage.
    """
    logger.info(f"Получена команда /start от пользователя {message.from_user.id}")

    # Передаем storage и storage_key в get_or_create_user для обновления активности и кэширования языка
    await get_or_create_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        storage_key=storage_key,  # Передаем StorageKey
        storage_obj=storage  # Передаем объект Storage
    )

    await state.clear() # Очищаем FSM-состояние

    # Вызываем функцию отображения меню, передавая storage и storage_key
    # _display_user_main_menu теперь сама получит язык из Storage
    await _display_user_main_menu(message, state, storage=storage, storage_key=storage_key)


@router.callback_query(F.data == "user_main_menu_back")
async def user_main_menu_back_callback(
        callback: CallbackQuery,
        state: FSMContext,
        storage: BaseStorage,  # aiogram сам предоставит объект хранилища
        storage_key: StorageKey  # aiogram сам предоставит StorageKey
):
    """
    Обрабатывает возврат пользователя в главное меню из любого подменю.
    Редактирует текущее сообщение, отображая главное меню пользователя,
    и сбрасывает FSM-состояние.
    Обновляет активность пользователя в БД и кэширует язык в Storage.
    """
    logger.info(f"Пользователь {callback.from_user.id} вернулся в главное меню.")

    # Передаем storage и storage_key в get_or_create_user для обновления активности и кэширования языка
    await get_or_create_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name,
        storage_key=storage_key,  # Передаем StorageKey
        storage_obj=storage  # Передаем объект Storage
    )

    await state.clear() # Очищаем FSM-состояние

    # Вызываем функцию отображения меню, передавая storage и storage_key
    # _display_user_main_menu теперь сама получит язык из Storage
    await _display_user_main_menu(callback, state, storage=storage, storage_key=storage_key)


# Пример хендлера, где нужно получить язык:
@router.message(F.text == "Мой язык")
async def get_my_language(
        message: Message,
        storage: BaseStorage,  # aiogram сам предоставит объект хранилища
        storage_key: StorageKey  # aiogram сам предоставит StorageKey
):
    """
    Обрабатывает запрос пользователя на получение информации о текущем языке.
    Получает язык из кэша (Storage) или БД.
    """
    # Получаем язык из кэша (или БД, если в кэше нет)
    current_lang = await get_user_language_code(message.from_user.id, storage_key, storage)
    await message.answer(f"Твой текущий язык: {current_lang}")


# Пример хендлера для смены языка:
@router.callback_query(F.data.startswith("set_lang_"))
async def change_user_language(
        callback: CallbackQuery,
        storage: BaseStorage,  # aiogram сам предоставит объект хранилища
        storage_key: StorageKey  # aiogram сам предоставит StorageKey
):
    """
    Обрабатывает выбор пользователя для смены языка.
    Обновляет язык в БД и кэше Storage.
    """
    user_id = callback.from_user.id
    new_lang = callback.data.split('_')[2] # Извлекаем код нового языка из callback_data

    # Обновляем язык в БД и кэше Storage
    updated_user = await update_user_language(user_id, new_lang, storage_key, storage)

    if updated_user:
        await callback.answer(f"Язык изменен на {updated_user.language_code}", show_alert=True)
        # Здесь можно добавить вызов get_localized_message для подтверждения
        # await callback.message.answer(get_localized_message("language_changed_success", updated_user.language_code))
    else:
        await callback.answer("Не удалось изменить язык.", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None) # Очищаем клавиатуру после выбора
