"""Core infrastructure module - shared across bot and web."""
from .config import (
    settings,
    ORDER_STATUS_KEYS,
    ACTIVE_ORDER_STATUS_KEYS,
    ORDER_FIELD_NAMES_KEYS,
    PHONE_NUMBER_REGEX,
    ORDER_FIELDS_CONFIG,
    ORDER_FIELD_MAP,
)
from .database import engine, AsyncSessionLocal, get_db_session
from .exceptions import (
    ApplicationError,
    OrderNotFoundError,
    UserNotFoundError,
    InvalidPhoneError,
    OrderValidationError,
    HelpMessageNotFoundError,
)

__all__ = [
    "settings",
    "ORDER_STATUS_KEYS",
    "ACTIVE_ORDER_STATUS_KEYS",
    "ORDER_FIELD_NAMES_KEYS",
    "PHONE_NUMBER_REGEX",
    "ORDER_FIELDS_CONFIG",
    "ORDER_FIELD_MAP",
    "engine",
    "AsyncSessionLocal",
    "get_db_session",
    "ApplicationError",
    "OrderNotFoundError",
    "UserNotFoundError",
    "InvalidPhoneError",
    "OrderValidationError",
    "HelpMessageNotFoundError",
]

