"""Help message service - business logic for help messages."""
import logging
from typing import Optional, List
from models import HelpMessage
from repositories.help_messages import HelpMessageRepository
logger = logging.getLogger(__name__)
class HelpMessageService:
    """Service layer for help message business logic."""
    def __init__(self, help_msg_repo: HelpMessageRepository) -> None:
        self._help_msg_repo = help_msg_repo
    async def create_help_message(
        self,
        message_text: str,
        language_code: str,
        is_active: bool = False,
    ) -> HelpMessage:
        """Create a new help message."""
        return await self._help_msg_repo.create(message_text, language_code, is_active)
    async def get_help_message(self, message_id: int) -> Optional[HelpMessage]:
        """Get help message by ID."""
        return await self._help_msg_repo.get_by_id(message_id)
    async def get_all_help_messages(self, language_code: Optional[str] = None) -> List[HelpMessage]:
        """Get all help messages optionally filtered by language."""
        return await self._help_msg_repo.get_all(language_code)
    async def get_active_help_message(self, language_code: str) -> Optional[HelpMessage]:
        """Get active help message for a language."""
        return await self._help_msg_repo.get_active_by_language(language_code)
    async def set_active_help_message(self, message_id: int, language_code: str) -> Optional[HelpMessage]:
        """Activate a help message."""
        return await self._help_msg_repo.set_active(message_id, language_code)
    async def deactivate_help_message(self, message_id: int) -> bool:
        """Deactivate a help message."""
        return await self._help_msg_repo.deactivate(message_id)
    async def delete_help_message(self, message_id: int) -> bool:
        """Delete a help message."""
        return await self._help_msg_repo.delete(message_id)
    async def update_help_message(self, message_id: int, **kwargs) -> bool:
        """Update a help message."""
        return await self._help_msg_repo.update(message_id, **kwargs)
