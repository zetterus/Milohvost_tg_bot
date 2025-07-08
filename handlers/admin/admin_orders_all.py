import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
# from aiogram.fsm.storage.base import BaseStorage, StorageKey # <-- УДАЛЕНО: Больше не нужны

from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from db import get_or_create_user # <-- НОВЫЙ ИМПОРТ для обновления активности
from localization import get_localized_message # <-- ДОБАВЛЕНО: Импорт для локализации

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_all_orders_start", IsAdmin())
async def admin_start_all_orders_view(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает начальное нажатие кнопки "Просмотреть все заказы".
    Очищает поисковый запрос из FSM и отображает первую страницу всех заказов.
    Обновляет активность пользователя в БД.
    """
    logger.info(f"Админ {callback.from_user.id} начал просмотр всех заказов.")

    # get_or_create_user теперь не требует storage_key и storage_obj
    await get_or_create_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
        last_name=callback.from_user.last_name
    )

    # Очищаем поисковый запрос при просмотре всех заказов, чтобы не мешал
    await state.update_data(search_query=None)

    await _display_orders_paginated(callback, state, lang=lang, current_page=1, is_search=False)


@router.callback_query(F.data.startswith("admin_all_orders_page:"), IsAdmin())
async def admin_paginate_all_orders(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str # <-- ДОБАВЛЕНО
):
    """
    Обрабатывает пагинацию для просмотра всех заказов.
    Извлекает номер страницы из callback_data и вызывает вспомогательную функцию для отображения.
    """
    try:
        # Ожидаемый формат: "admin_all_orders_page:1"
        current_page = int(callback.data.split(':')[1])
    except (ValueError, IndexError):
        logger.error(
            f"Админ {callback.from_user.id}: Неверный формат callback_data для пагинации всех заказов: {callback.data}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True) # <-- Локализовано
        return

    logger.info(f"Админ {callback.from_user.id} переключает страницу всех заказов на {current_page}.")
    await _display_orders_paginated(callback, state, lang=lang, current_page=current_page, is_search=False)
