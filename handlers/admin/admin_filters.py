import logging
from typing import Union

from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from config import ADMIN_IDS  # Предполагается, что ADMIN_IDS - это список или множество ID администраторов

logger = logging.getLogger(__name__)


class IsAdmin(BaseFilter):
    """
    Пользовательский фильтр для проверки, является ли отправитель сообщения или callback-запроса администратором.
    Определяет администраторов по их ID, перечисленным в ADMIN_IDS из файла конфигурации.
    Если пользователь не является админом, логирует попытку несанкционированного доступа.
    """

    async def __call__(self, update: Union[Message, CallbackQuery]) -> bool:
        """
        Метод проверки фильтра.

        Args:
            update (Union[Message, CallbackQuery]): Объект обновления (сообщение или callback-запрос).

        Returns:
            bool: True, если пользователь является администратором, False в противном случае.
        """
        user_id = update.from_user.id
        user_full_name = update.from_user.full_name

        # Проверяем, находится ли ID пользователя в списке администраторов
        if user_id in ADMIN_IDS:
            return True

        # Если пользователь не админ, логируем попытку несанкционированного доступа
        access_attempt_details = "неизвестный тип доступа"

        if isinstance(update, Message):
            # Если это сообщение, логируем его текст
            access_attempt_details = f"доступ к сообщению: '{update.text}'"
        elif isinstance(update, CallbackQuery):
            # Если это callback-запрос, логируем его данные
            access_attempt_details = f"доступ к callback_data: '{update.data}'"

        logger.warning(
            f"Неавторизованный доступ: Пользователь {user_full_name} (ID: {user_id}) "
            f"попытался получить {access_attempt_details}."
        )
        return False
