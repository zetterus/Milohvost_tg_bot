"""User service - business logic for users."""
import logging
from typing import Optional
from models import User
from repositories.users import UserRepository
logger = logging.getLogger(__name__)
class UserService:
    """Service layer for user business logic."""
    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo
    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
    ) -> User:
        """Get existing user or create new one."""
        return await self._user_repo.get_or_create(user_id, username, first_name, last_name)
    async def get_user(self, user_id: int) -> Optional[User]:
        """Get user by ID."""
        return await self._user_repo.get_by_id(user_id)
    async def get_user_language(self, user_id: int) -> str:
        """Get user language, default is 'uk'."""
        return await self._user_repo.get_language(user_id)
    async def change_user_language(self, user_id: int, language_code: str) -> Optional[User]:
        """Change user language."""
        return await self._user_repo.update_language(user_id, language_code)
    async def get_notifications_enabled(self, user_id: int) -> Optional[bool]:
        """Check if user has notifications enabled."""
        return await self._user_repo.get_notifications_enabled(user_id)
    async def toggle_notifications(self, user_id: int, enabled: bool) -> Optional[User]:
        """Toggle user notifications."""
        return await self._user_repo.update_notifications(user_id, enabled)
