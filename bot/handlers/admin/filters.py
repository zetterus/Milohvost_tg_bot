"""Admin filter - updated to use core.settings instead of old config.ADMIN_IDS."""
import logging
from typing import Union
from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from core.config import settings
logger = logging.getLogger(__name__)
class IsAdmin(BaseFilter):
    """Filter that allows only admins configured in settings.admin_ids."""
    async def __call__(self, update: Union[Message, CallbackQuery]) -> bool:
        user_id = update.from_user.id
        if user_id in settings.admin_ids:
            return True
        update_info = f"message: '{update.text}'" if isinstance(update, Message) else f"callback: '{update.data}'"
        logger.warning(f"Unauthorized access attempt by {update.from_user.full_name} (ID: {user_id}) - {update_info}")
        return False
