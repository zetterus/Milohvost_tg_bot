import logging
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from typing import Union
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

class IsAdmin(BaseFilter):
    async def __call__(self, update: Union[Message, CallbackQuery]) -> bool:
        if update.from_user.id in ADMIN_IDS:
            return True

        # Если это не админ, логируем попытку доступа
        user_id = update.from_user.id
        access_attempt_info = "Неизвестный доступ"  # Дефолтное сообщение

        if isinstance(update, Message):
            access_attempt_info = f"доступ к сообщению: '{update.text}'"
        elif isinstance(update, CallbackQuery):
            access_attempt_info = f"доступ к callback_data: '{update.data}'"

        logger.warning(
            f"Неадмин {user_id} ({update.from_user.full_name}) попытался получить {access_attempt_info}.")
        return False
