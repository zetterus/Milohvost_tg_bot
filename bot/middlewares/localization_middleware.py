"""Localization middleware - updated to use UserRepository instead of raw db.py calls."""
import logging
from typing import Callable, Dict, Any, Awaitable, Optional
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, User
from core.database import get_db_session
from repositories.users import UserRepository
logger = logging.getLogger(__name__)
def _get_user_from_event(event: Update) -> Optional[User]:
    """Safely extract User object from various event types."""
    if event.message:
        return event.message.from_user
    if event.callback_query:
        return event.callback_query.from_user
    if event.edited_message:
        return event.edited_message.from_user
    if event.inline_query:
        return event.inline_query.from_user
    if event.chosen_inline_result:
        return event.chosen_inline_result.from_user
    if event.pre_checkout_query:
        return event.pre_checkout_query.from_user
    if event.poll_answer:
        return event.poll_answer.user
    return None
class LocalizationMiddleware(BaseMiddleware):
    """Middleware that resolves user language and injects it as lang= into handlers."""
    async def __call__(
            self,
            handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: Update,
            data: Dict[str, Any]
    ) -> Any:
        user = _get_user_from_event(event)
        if user is None:
            logger.debug(f"LocalizationMiddleware: Could not get user from {event.event_type}. Skipping.")
            return await handler(event, data)
        async with get_db_session() as session:
            user_repo = UserRepository(session)
            lang = await user_repo.get_language(user.id)
        data["lang"] = lang
        logger.debug(f"LocalizationMiddleware: User {user.id} language = '{lang}'")
        return await handler(event, data)
