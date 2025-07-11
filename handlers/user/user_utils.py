import logging
from typing import Union # Dict, Any больше не нужны

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
# from aiogram.fsm.storage.base import BaseStorage, StorageKey # Больше не нужны

from aiogram.utils.keyboard import InlineKeyboardBuilder # <-- ДОБАВЛЕНО
from aiogram.enums import ParseMode # <-- ДОБАВЛЕНО

from localization import get_localized_message # Импортируем функцию локализации
from db import update_user_language # Импортируем функции БД (get_user_language_code удален, так как не используется)

logger = logging.getLogger(__name__)
router = Router() # <-- Основной роутер для user_utils.py

# --- Вспомогательная функция для отображения главного меню пользователя ---
async def _display_user_main_menu(
    update_object: Union[Message, CallbackQuery],
    state: FSMContext,
    lang: str
):
    """
    Отображает главное меню для пользователя, сбрасывая его FSM-состояние.
    Сообщение отправляется или редактируется в зависимости от типа объекта обновления.
    Использует локализованные тексты.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение меню.
    :param state: FSMContext для управления состоянием пользователя.
    :param lang: Код языка для локализации текстов.
    """
    user_id = update_object.from_user.id
    logger.info(f"Пользователь {user_id} переходит в главное меню (язык: {lang}).")

    await state.clear()  # Очищаем все данные из FSM, чтобы начать с чистого листа

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_make_order", lang), callback_data="make_order")
    keyboard.button(text=get_localized_message("button_view_my_orders", lang), callback_data="view_my_orders")
    keyboard.button(text=get_localized_message("button_get_help", lang), callback_data="get_help")
    keyboard.button(text=get_localized_message("button_my_language", lang), callback_data="show_language_options")
    keyboard.adjust(1)

    menu_text = get_localized_message("welcome", lang)

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

# --- ХЕНДЛЕР для отображения опций языка ---
@router.callback_query(F.data == "show_language_options")
async def show_language_options_callback(
    callback: CallbackQuery,
    lang: str
):
    """
    Показывает пользователю опции для смены языка.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил опции языка (текущий: {lang}).")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🇺🇦 Українська", callback_data="set_lang_uk")
    keyboard.button(text="🇬🇧 English", callback_data="set_lang_en")
    keyboard.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang), callback_data="user_main_menu_back"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        get_localized_message("choose_language_prompt", lang),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

# --- Хендлер для получения информации о языке (перемещен из main_menu.py) ---
@router.message(F.text == "Мой язык")
async def get_my_language(
        message: Message,
        lang: str # <-- ОСТАВЛЕНО
):
    """
    Обрабатывает запрос пользователя на получение информации о текущем языке.
    """
    # get_user_language_code теперь не требует storage_key и storage_obj
    # current_lang = await get_user_language_code(message.from_user.id) # Если нужно получить из БД
    await message.answer(get_localized_message("your_current_language", lang).format(current_lang=lang))


# --- Хендлер для смены языка (перемещен из main_menu.py) ---
@router.callback_query(F.data.startswith("set_lang_"))
async def change_user_language(
        callback: CallbackQuery,
        lang: str # <-- ОСТАВЛЕНО
):
    """
    Обрабатывает выбор пользователя для смены языка.
    Обновляет язык в БД.
    """
    user_id = callback.from_user.id
    new_lang = callback.data.split('_')[2] # Извлекаем код нового языка из callback_data

    updated_user = await update_user_language(user_id, new_lang)

    if updated_user:
        await callback.answer(get_localized_message("language_changed_success_alert", updated_user.language_code),
                              show_alert=True)
        await callback.message.delete()
    else:
        await callback.answer(get_localized_message("language_change_failed_alert", lang), show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=None)