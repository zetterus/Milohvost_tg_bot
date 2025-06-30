import logging
import urllib.parse

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import StateFilter
from aiogram.utils.keyboard import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext

from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from .admin_states import AdminStates

logger = logging.getLogger(__name__)
router = Router()  # Локальный роутер для этого модуля


@router.callback_query(F.data == "admin_find_orders", IsAdmin())
async def admin_find_orders_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает нажатие кнопки "Найти заказы 🔍".
    Запрашивает у пользователя поисковый запрос и переводит в состояние ожидания ввода.
    """
    logger.info(f"Админ {callback.from_user.id} начал поиск заказов. Текущее состояние: {await state.get_state()}")

    await bot.answer_callback_query(callback.id)

    await state.set_state(AdminStates.waiting_for_search_query)
    logger.info(f"Состояние админа {callback.from_user.id} установлено в {await state.get_state()}")

    await bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        text="Пожалуйста, введите ID заказа, часть имени пользователя или часть текста заказа для поиска:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Отмена", callback_data="admin_panel_back")]
        ]),
        parse_mode="HTML"
    )


@router.message(StateFilter(AdminStates.waiting_for_search_query), IsAdmin())
async def admin_process_search_query(message: Message, state: FSMContext):
    """
    Обрабатывает текстовое сообщение с поисковым запросом.
    Выполняет поиск и отображает результаты.
    """
    search_query = message.text.strip()
    logger.info(f"Админ {message.from_user.id} ввел поисковый запрос: '{search_query}'.")

    await state.update_data(search_query=search_query)  # Сохраняем поисковый запрос в FSM-контексте

    # Переходим к отображению первой страницы результатов поиска.
    await _display_orders_paginated(message, state, current_page=1, is_search=True)


@router.callback_query(F.data.startswith("admin_search_page:"), IsAdmin())
async def admin_view_search_results_paginated_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает пагинацию результатов поиска.
    """
    parts = callback.data.split(':')
    if len(parts) < 3:  # Ожидаем минимум 3 части: "admin_search_page", page_num, encoded_query
        logger.error(f"Неверный формат callback_data для пагинации поиска: {callback.data}")
        await callback.answer("Ошибка при обработке страницы.", show_alert=True)
        return

    try:
        current_page = int(parts[1])
        encoded_query = parts[2]
        search_query = urllib.parse.unquote_plus(encoded_query)
    except (ValueError, IndexError):
        logger.error(f"Неверный формат callback_data для пагинации поиска: {callback.data}")
        await callback.answer("Ошибка при обработке страницы.", show_alert=True)
        return

    logger.info(
        f"Админ {callback.from_user.id} переключает страницу поиска на {current_page} с запросом '{search_query}'.")
    await state.update_data(search_query=search_query)  # Убедимся, что search_query снова в FSM
    await _display_orders_paginated(callback, state, current_page=current_page, is_search=True)
