import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey # <-- НОВЫЙ ИМПОРТ

from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from localization import get_localized_message # <-- НОВЫЙ ИМПОРТ

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_all_orders_start", IsAdmin())
async def admin_start_all_orders_view(
    callback: CallbackQuery,
    state: FSMContext,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО
    storage_key: StorageKey # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает начальное нажатие кнопки "Просмотреть все заказы".
    Очищает поисковый запрос из FSM и отображает первую страницу всех заказов.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} начал просмотр всех заказов.")
    # Очищаем поисковый запрос при просмотре всех заказов, чтобы не мешал
    await state.update_data(search_query=None)

    # Передаем storage и storage_key в _display_orders_paginated
    await _display_orders_paginated(callback, state, storage=storage, storage_key=storage_key, current_page=1, is_search=False)


@router.callback_query(F.data.startswith("admin_all_orders_page:"), IsAdmin())
async def admin_paginate_all_orders(
    callback: CallbackQuery,
    state: FSMContext,
    storage: BaseStorage,  # <-- ДОБАВЛЕНО
    storage_key: StorageKey # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает пагинацию для просмотра всех заказов.
    Извлекает номер страницы из callback_data и вызывает вспомогательную функцию для отображения.
    """
    user_id = callback.from_user.id
    # Получаем язык пользователя из Storage для локализации сообщения об ошибке
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk') # По умолчанию 'uk'

    try:
        # Ожидаемый формат: "admin_all_orders_page:1"
        current_page = int(callback.data.split(':')[1])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {user_id}: Неверный формат callback_data для пагинации всех заказов: {callback.data}")
        # Локализованное сообщение об ошибке
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    logger.info(f"Админ {user_id} переключает страницу всех заказов на {current_page}.")
    # Передаем storage и storage_key в _display_orders_paginated
    await _display_orders_paginated(callback, state, storage=storage, storage_key=storage_key, current_page=current_page, is_search=False)
