import logging
from typing import Union # Импортируем Union для type hinting

from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey # Импорт BaseStorage и StorageKey
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode # Явно импортируем ParseMode

from localization import get_localized_message # Импортируем функцию локализации

logger = logging.getLogger(__name__)


# Функция для создания клавиатуры главного меню пользователя
def _get_user_main_menu_keyboard(lang: str) -> InlineKeyboardBuilder:
    """
    Создает инлайн-клавиатуру для главного меню пользователя, используя локализованные тексты.
    """
    builder = InlineKeyboardBuilder()
    builder.button(text=get_localized_message("button_make_order", lang), callback_data="make_order")
    builder.button(text=get_localized_message("button_view_my_orders", lang), callback_data="view_my_orders")
    builder.button(text=get_localized_message("button_get_help", lang), callback_data="get_help")
    builder.adjust(1) # Кнопки будут располагаться по одной в ряд
    return builder


async def _display_user_main_menu(
    update_object: Union[Message, CallbackQuery],
    state: FSMContext,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО: получаем объект хранилища
    storage_key: StorageKey # <-- ДОБАВЛЕНО: получаем StorageKey
):
    """
    Отображает главное меню для пользователя, сбрасывая его FSM-состояние.
    Сообщение отправляется или редактируется в зависимости от типа объекта обновления.
    Использует локализацию, получая язык из Storage.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение меню.
    :param state: FSMContext для управления состоянием пользователя.
    :param storage: Объект Storage для доступа к персистентным данным пользователя.
    :param storage_key: StorageKey для идентификации данных пользователя.
    """
    user_id = update_object.from_user.id # Получаем ID пользователя для логирования
    logger.info(f"Пользователь {user_id} переходит в главное меню.")

    await state.clear()  # Очищаем все данные из FSM, чтобы начать с чистого листа

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk') # По умолчанию 'uk', если язык не найден в Storage

    # Используем новую внутреннюю функцию для создания клавиатуры
    keyboard = _get_user_main_menu_keyboard(lang)
    reply_markup = keyboard.as_markup()

    # Локализованный текст приветствия/меню
    menu_text = get_localized_message("welcome", lang) # Используем ключ "welcome" из JSON

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        # Отвечаем на CallbackQuery, чтобы убрать "часики"
        await update_object.answer()
        # Редактируем сообщение, так как оно уже существует
        await update_object.message.edit_text(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
