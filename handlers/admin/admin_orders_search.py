import logging
import urllib.parse

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from .admin_states import AdminStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_find_orders", IsAdmin())
async def admin_find_orders_callback(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Обрабатывает нажатие кнопки "Найти заказы 🔍".
    Запрашивает у пользователя поисковый запрос и переводит в состояние ожидания ввода.
    """
    logger.info(f"Админ {callback.from_user.id} начал поиск заказов. Текущее состояние: {await state.get_state()}")

    # Отправляем ответ на callback, чтобы убрать "часики"
    await callback.answer()

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
    Сохраняет запрос в FSMContext и отображает первую страницу результатов поиска.
    """
    search_query = message.text.strip()
    logger.info(f"Админ {message.from_user.id} ввел поисковый запрос: '{search_query}'.")

    # Сохраняем поисковый запрос в FSM-контексте
    await state.update_data(search_query=search_query)

    # Переходим к отображению первой страницы результатов поиска.
    # Используем message как объект-носитель для chat_id/message_id, так как это хэндлер сообщения.
    await _display_orders_paginated(message, state, current_page=1, is_search=True)


@router.callback_query(F.data.startswith("admin_search_page:"), IsAdmin())
async def admin_view_search_results_paginated_callback(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает пагинацию результатов поиска.
    Извлекает номер страницы и поисковый запрос из callback_data.
    """
    try:
        # Ожидаемый формат: "admin_search_page:page_num:encoded_query"
        parts = callback.data.split(':', 2)  # Разделяем только на 3 части: префикс, номер страницы, запрос
        current_page = int(parts[1])
        encoded_query = parts[2]
        search_query = urllib.parse.unquote_plus(encoded_query)
    except (ValueError, IndexError):
        logger.error(
            f"Админ {callback.from_user.id}: Неверный формат callback_data для пагинации поиска: {callback.data}")
        await callback.answer("Ошибка при обработке страницы.", show_alert=True)
        return

    logger.info(
        f"Админ {callback.from_user.id} переключает страницу поиска на {current_page} с запросом '{search_query}'.")
    # Убедимся, что search_query актуален в FSM для последующих операций (например, просмотра деталей заказа)
    await state.update_data(search_query=search_query)
    await _display_orders_paginated(callback, state, current_page=current_page, is_search=True)
