"""User repository - data access layer for users."""
import logging
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from models import User
from .base import AbstractRepository
logger = logging.getLogger(__name__)
class UserRepository(AbstractRepository[User]):
    """Repository for User entities."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
    async def get_or_create(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Get user or create if doesn't exist."""
        stmt = select(User).where(User.user_id == user_id)
        result = await self._session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.last_activity_at = func.now()
            logger.debug(f"User {user_id} updated")
        else:
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )
            self._session.add(user)
            logger.info(f"New user {user_id} created")
        await self._session.flush()
        await self._session.refresh(user)
        return user
    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Get user by Telegram user_id."""
        stmt = select(User).where(User.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    async def get_all(self) -> list[User]:
        """Get all users."""
        stmt = select(User)
        result = await self._session.execute(stmt)
        return result.scalars().all()
    async def get_language(self, user_id: int) -> str:
        """Get user's language, default 'uk'."""
        user = await self.get_by_id(user_id)
        return user.language_code if user else "uk"
    async def update_language(self, user_id: int, language_code: str) -> Optional[User]:
        """Update user's language."""
        user = await self.get_by_id(user_id)
        if user:
            user.language_code = language_code
            user.last_activity_at = func.now()
            logger.info(f"User {user_id} language updated to {language_code}")
            return user
        logger.warning(f"User {user_id} not found for language update")
        return None
    async def get_notifications_enabled(self, user_id: int) -> Optional[bool]:
        """Get user's notification status."""
        user = await self.get_by_id(user_id)
        return user.notifications_enabled if user else None
    async def update_notifications(self, user_id: int, enabled: bool) -> Optional[User]:
        """Update user's notification status."""
        user = await self.get_by_id(user_id)
        if user:
            user.notifications_enabled = enabled
            user.last_activity_at = func.now()
            logger.info(f"User {user_id} notifications set to {enabled}")
            return user
        logger.warning(f"User {user_id} not found for notifications update")
        return None
    async def update(self, user_id: int, **kwargs) -> bool:
        """Update user with arbitrary kwargs."""
        user = await self.get_by_id(user_id)
        if user:
            for key, value in kwargs.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            user.last_activity_at = func.now()
            return True
        return False
    async def delete(self, user_id: int) -> bool:
        """Delete user by ID."""
        user = await self.get_by_id(user_id)
        if user:
            await self._session.delete(user)
            logger.info(f"User {user_id} deleted")
            return True
        logger.warning(f"User {user_id} not found for deletion")
        return False
    async def create(self, **kwargs) -> User:
        """Create a new user - use get_or_create instead."""
        raise NotImplementedError("Use get_or_create for User entities")
