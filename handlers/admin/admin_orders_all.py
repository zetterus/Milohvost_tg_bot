import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, BufferedInputFile # ИЗМЕНЕНО: Импортируем BufferedInputFile
from aiogram.fsm.context import FSMContext

from .admin_utils import _display_orders_paginated
from .admin_filters import IsAdmin
from db import get_or_create_user, get_all_orders
from localization import get_localized_message
from .admin_export import generate_orders_csv

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_all_orders_start", IsAdmin())
async def admin_start_all_orders_view(
        callback: CallbackQuery,
        state: FSMContext,
        lang: str
):
    """
    Обрабатывает начальное нажатие кнопки "Просмотреть все заказы".
    Очищает поисковый запрос из FSM и отображает первую страницу всех заказов.
    Обновляет активность пользователя в БД.
    """
    logger.info(f"Админ {callback.from_user.id} начал просмотр всех заказов.")

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
        lang: str
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
        alert_text = get_localized_message("error_invalid_callback_data", lang)
        await callback.answer(alert_text, show_alert=True)
        return

    logger.info(f"Админ {callback.from_user.id} переключает страницу всех заказов на {current_page}.")
    await _display_orders_paginated(callback, state, lang=lang, current_page=current_page, is_search=False)


@router.callback_query(F.data == "export_all_orders_csv", IsAdmin())
async def export_all_orders_csv_callback(
        callback: CallbackQuery,
        bot: Bot,
        lang: str
):
    """
    Обрабатывает запрос на выгрузку всех заказов в CSV.
    """
    user_id = callback.from_user.id
    logger.info(f"Админ {user_id} запросил выгрузку всех заказов в CSV.")

    await callback.answer(get_localized_message("thank_you_processing", lang), show_alert=False)

    try:
        all_orders, total_count = await get_all_orders(offset=0, limit=None)

        if not all_orders:
            await callback.message.answer(get_localized_message("export_csv_no_data_alert", lang))
            await callback.answer(get_localized_message("export_csv_no_data_alert", lang), show_alert=True)
            logger.warning(f"Админ {user_id}: Нет данных для экспорта всех заказов в CSV.")
            return

        csv_file_in_memory = await generate_orders_csv(all_orders, lang)

        # ИЗМЕНЕНО: Используем BufferedInputFile вместо FSInputFile
        await bot.send_document(
            chat_id=user_id,
            document=BufferedInputFile(csv_file_in_memory.getvalue(), filename="all_orders.csv"), # .getvalue() для получения байтов
            caption=get_localized_message("export_csv_success_alert", lang)
        )
        logger.info(f"Админу {user_id} успешно отправлен CSV-файл со всеми заказами.")
        await callback.answer(get_localized_message("export_csv_success_alert", lang), show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка при выгрузке всех заказов в CSV для админа {user_id}: {e}", exc_info=True)
        await callback.message.answer(get_localized_message("export_csv_error_alert", lang))
        await callback.answer(get_localized_message("export_csv_error_alert", lang), show_alert=True)
