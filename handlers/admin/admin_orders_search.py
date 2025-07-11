import logging
import urllib.parse

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from db import get_or_create_user
from .admin_filters import IsAdmin
from .admin_states import AdminStates
from .admin_utils import _display_orders_paginated, _display_admin_main_menu
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_find_orders", IsAdmin())
async def admin_find_orders_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает нажатие кнопки "Найти заказы 🔍".
    Запрашивает у пользователя поисковый запрос и переводит в состояние ожидания ввода.
    Обновляет активность пользователя в БД.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} начал поиск заказов. Текущее состояние: {await state.get_state()}")

    await get_or_create_user(
        user_id=user_id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name
    )

    await callback.answer()

    await state.set_state(AdminStates.waiting_for_search_query)
    logger.info(f"Состояние админа {user_id} установлено в {await state.get_state()}")

    # Используем новый локализованный текст для запроса поискового запроса
    # и новую кнопку для отмены поиска.
    await callback.message.edit_text(
        text=get_localized_message("admin_prompt_search_query", lang),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=get_localized_message("admin_cancel_search_button", lang),
                                  callback_data="admin_panel_back")]
        ])
    )


@router.message(AdminStates.waiting_for_search_query, IsAdmin())
async def process_search_query(
        message: Message,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает введенный админом поисковый запрос.
    Сохраняет запрос и отображает результаты поиска с пагинацией.
    """
    user_id = message.from_user.id
    search_query = message.text.strip()
    logger.info(f"Админ {user_id} ввел поисковый запрос: '{search_query}'.")

    if not search_query:
        await message.answer(get_localized_message("admin_prompt_search_query", lang), parse_mode=ParseMode.HTML)
        return

    await state.update_data(search_query=search_query)

    await _display_orders_paginated(message, state, current_page=1, lang=lang, is_search=True)


@router.callback_query(F.data.startswith("admin_search_page:"), IsAdmin())
async def admin_search_pagination_callback(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает нажатия кнопок пагинации для результатов поиска.
    """
    user_id = callback.from_user.id
    try:
        parts = callback.data.split(":")
        page = int(parts[1])
        # Декодируем поисковый запрос, если он есть
        search_query_encoded = parts[2] if len(parts) > 2 else ""
        search_query = urllib.parse.unquote_plus(search_query_encoded)
    except (ValueError, IndexError):
        logger.error(f"Админ {user_id}: Неверный формат callback_data для пагинации поиска: {callback.data}")
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {user_id} переключает страницу поиска на {page} для запроса '{search_query}'.")

    # Обновляем поисковый запрос в FSM, если он был передан через callback
    if search_query:
        await state.update_data(search_query=search_query)

    await _display_orders_paginated(callback, state, current_page=page, lang=lang, is_search=True)

