import logging
import urllib.parse

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.enums import ParseMode

from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from .admin_states import AdminStates
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_find_orders", IsAdmin())
async def admin_find_orders_callback(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО
    storage_key: StorageKey # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает нажатие кнопки "Найти заказы 🔍".
    Запрашивает у пользователя поисковый запрос и переводит в состояние ожидания ввода.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} начал поиск заказов. Текущее состояние: {await state.get_state()}")

    # Получаем язык пользователя из Storage для локализации
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk') # По умолчанию 'uk'

    await callback.answer() # Отправляем ответ на callback, чтобы убрать "часики"

    await state.set_state(AdminStates.waiting_for_search_query)
    logger.info(f"Состояние админа {user_id} установлено в {await state.get_state()}")

    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text=get_localized_message("admin_prompt_search_query", lang), # <-- Локализовано
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="admin_panel_back")] # <-- Локализовано
        ]),
        parse_mode=ParseMode.HTML # Используем ParseMode.HTML вместо "HTML"
    )


@router.message(StateFilter(AdminStates.waiting_for_search_query), IsAdmin())
async def admin_process_search_query(
    message: Message,
    state: FSMContext,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО
    storage_key: StorageKey # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает текстовое сообщение с поисковым запросом.
    Сохраняет запрос в FSMContext и отображает первую страницу результатов поиска.
    """
    user_id = message.from_user.id
    search_query = message.text.strip()
    logger.info(f"Админ {user_id} ввел поисковый запрос: '{search_query}'.")

    # Сохраняем поисковый запрос в FSM-контексте
    await state.update_data(search_query=search_query)

    # Переходим к отображению первой страницы результатов поиска.
    # Передаем storage и storage_key
    await _display_orders_paginated(message, state, storage=storage, storage_key=storage_key, current_page=1, is_search=True)


@router.callback_query(F.data.startswith("admin_search_page:"), IsAdmin())
async def admin_view_search_results_paginated_callback(
    callback: CallbackQuery,
    state: FSMContext,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО
    storage_key: StorageKey # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает пагинацию результатов поиска.
    Извлекает номер страницы и поисковый запрос из callback_data.
    """
    user_id = callback.from_user.id
    # Получаем язык пользователя из Storage для локализации сообщения об ошибке
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk') # По умолчанию 'uk'

    try:
        # Ожидаемый формат: "admin_search_page:page_num:encoded_query"
        parts = callback.data.split(':', 2)  # Разделяем только на 3 части: префикс, номер страницы, запрос
        current_page = int(parts[1])
        encoded_query = parts[2]
        search_query = urllib.parse.unquote_plus(encoded_query)
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для пагинации поиска: {callback.data}")
        # Локализованное сообщение об ошибке
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(
        f"Админ {user_id} переключает страницу поиска на {current_page} с запросом '{search_query}'.")
    # Убедимся, что search_query актуален в FSM для последующих операций (например, просмотра деталей заказа)
    await state.update_data(search_query=search_query)
    # Передаем storage и storage_key
    await _display_orders_paginated(callback, state, storage=storage, storage_key=storage_key, current_page=current_page, is_search=True)
