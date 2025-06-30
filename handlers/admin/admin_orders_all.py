import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin

logger = logging.getLogger(__name__)
router = Router()  # Локальный роутер для этого модуля


@router.callback_query(F.data == "admin_all_orders_start", IsAdmin())
async def admin_start_all_orders_view(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает начальное нажатие кнопки "Просмотреть все заказы".
    Очищает поисковый запрос из FSM и отображает первую страницу всех заказов.
    """
    logger.info(f"Админ {callback.from_user.id} начал просмотр всех заказов.")
    await state.update_data(search_query=None)  # Очищаем поисковый запрос при просмотре всех заказов

    await _display_orders_paginated(callback, state, current_page=1, is_search=False)


@router.callback_query(F.data.startswith("admin_all_orders_page:"), IsAdmin())
async def admin_paginate_all_orders(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает пагинацию для просмотра всех заказов.
    """
    parts = callback.data.split(':')

    if len(parts) < 2:
        logger.error(f"Неверный формат callback_data для пагинации всех заказов: {callback.data}")
        await callback.answer("Ошибка при обработке страницы.", show_alert=True)
        return

    try:
        current_page = int(parts[1])
    except (ValueError, IndexError):
        logger.error(f"Неверный формат callback_data для пагинации всех заказов: {callback.data}")
        await callback.answer("Ошибка при обработке страницы.", show_alert=True)
        return

    logger.info(f"Админ {callback.from_user.id} переключает страницу всех заказов на {current_page}.")
    await _display_orders_paginated(callback, state, current_page=current_page, is_search=False)
