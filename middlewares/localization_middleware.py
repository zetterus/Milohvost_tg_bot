import logging
from typing import Callable, Dict, Any, Awaitable, Optional

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, Update, User, InlineQuery, ChosenInlineResult, PreCheckoutQuery, \
    PollAnswer  # Добавлены необходимые импорты

from db import get_user_language_code

logger = logging.getLogger(__name__)


def _get_user_from_event(event: Update) -> Optional[User]:
    """
    Вспомогательная функция для безопасного извлечения объекта User из различных типов обновлений.
    """
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
    # Добавьте другие типы обновлений, если ваш бот их обрабатывает и им нужен from_user
    return None


class LocalizationMiddleware(BaseMiddleware):
    """
    Middleware для определения языка пользователя и передачи его в хендлеры.
    Получает язык из БД.
    """

    async def __call__(
            self,
            handler: Callable[[Message | CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: Update,  # Middleware перехватывает все объекты Update
            data: Dict[str, Any]
    ) -> Any:
        """
        Обрабатывает входящее событие, определяет язык пользователя
        и добавляет его в 'data' для инъекции в хендлеры.
        """
        user = _get_user_from_event(event)

        if user is None:
            # Если не удалось получить пользователя из события,
            # возможно, это обновление, которое не содержит from_user (например, chat_member, my_chat_member)
            # или это не тот тип обновления, который мы хотим локализовать.
            # В этом случае просто пропускаем middleware и передаем управление дальше.
            logger.debug(
                f"LocalizationMiddleware: Не удалось получить user из события типа {event.event_type}. Пропускаю локализацию.")
            return await handler(event, data)

        user_id = user.id

        # Получаем язык напрямую из БД
        lang = await get_user_language_code(user_id)

        # Добавляем язык в data, чтобы он был доступен как 'lang' в хендлерах
        data["lang"] = lang
        logger.debug(f"LocalizationMiddleware: Для пользователя {user_id} определен язык '{lang}'.")

        # Передаем управление следующему middleware или хендлеру
        return await handler(event, data)
