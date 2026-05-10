"""Help message repository - data access layer for help messages."""
import logging
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from models import HelpMessage
from .base import AbstractRepository
logger = logging.getLogger(__name__)
class HelpMessageRepository(AbstractRepository[HelpMessage]):
    """Repository for HelpMessage entities."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
    async def create(
        self,
        message_text: str,
        language_code: str,
        is_active: bool = False,
    ) -> HelpMessage:
        """Create a new help message."""
        if is_active:
            active_msgs = await self.get_active_by_language(language_code)
            if active_msgs:
                active_msgs.is_active = False
                await self._session.flush()
        msg = HelpMessage(
            message_text=message_text,
            language_code=language_code,
            is_active=is_active,
        )
        self._session.add(msg)
        await self._session.flush()
        await self._session.refresh(msg)
        logger.info(f"New help message ID {msg.id} for {language_code}")
        return msg
    async def get_by_id(self, message_id: int) -> Optional[HelpMessage]:
        """Get help message by ID."""
        stmt = select(HelpMessage).where(HelpMessage.id == message_id)
        stmt = select(HelpMessage).where(HelpMessage.id == message_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    async def get_all(self, language_code: Optional[str] = None) -> List[HelpMessage]:
        """Get all help messages, optionally filtered by language."""
        stmt = select(HelpMessage).order_by(HelpMessage.created_at.desc())
        if language_code:
            stmt = stmt.where(HelpMessage.language_code == language_code)
        result = await self._session.execute(stmt)
        return result.scalars().all()
    async def get_active_by_language(self, language_code: str) -> Optional[HelpMessage]:
        """Get active help message for a language."""
        stmt = select(HelpMessage).where(
            HelpMessage.is_active == True,
            HelpMessage.language_code == language_code,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    async def set_active(self, message_id: int, language_code: str) -> Optional[HelpMessage]:
        """Set a message as active for its language."""
        msg = await self.get_by_id(message_id)
        if not msg:
            logger.warning(f"Help message {message_id} not found")
            return None
        if msg.language_code != language_code:
            logger.warning(f"Language mismatch for message {message_id}")
            return None
        active = await self.get_active_by_language(language_code)
        if active and active.id != message_id:
            active.is_active = False
            await self._session.flush()
        msg.is_active = True
        msg.updated_at = func.now()
        logger.info(f"Help message {message_id} activated")
        return msg
    async def deactivate(self, message_id: int) -> bool:
        """Deactivate a help message."""
        msg = await self.get_by_id(message_id)
        if msg:
            msg.is_active = False
            msg.updated_at = func.now()
            logger.info(f"Help message {message_id} deactivated")
            return True
        logger.warning(f"Help message {message_id} not found")
        return False
    async def update(self, message_id: int, **kwargs) -> bool:
        """Update help message."""
        msg = await self.get_by_id(message_id)
        if msg:
            for key, value in kwargs.items():
                if hasattr(msg, key) and key != "id":
                    setattr(msg, key, value)
            msg.updated_at = func.now()
            return True
        return False
    async def delete(self, message_id: int) -> bool:
        """Delete help message."""
        msg = await self.get_by_id(message_id)
        if msg:
            await self._session.delete(msg)
            logger.info(f"Help message {message_id} deleted")
            return True
        logger.warning(f"Help message {message_id} not found")
        return False
