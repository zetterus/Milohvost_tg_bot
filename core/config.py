"""Settings module using pydantic-settings for configuration management."""
import re
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
class Settings(BaseSettings):
    """Application settings loaded from .env file and environment variables."""
    bot_token: str
    admin_ids: list[int] = []
    database_name: str = "orders_bot.db"
    logging_level: str = "INFO"
    orders_per_page: int = 10
    max_preview_text_length: int = 30
    user_orders_per_page: int = 5
    web_form_user_id: int = -1
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            return [int(id_.strip()) for id_ in v.split(",") if id_.strip()]
        if isinstance(v, list):
            return [int(id_) for id_ in v]
        return []
settings = Settings()
ORDER_STATUS_KEYS = ['new', 'stockcheck', 'confirmed', 'paid', 'tosupplier', 'awaitingship', 'shipped', 'intransit', 'onhold', 'delivered', 'cancelled', 'returned']
ACTIVE_ORDER_STATUS_KEYS = ['new', 'stockcheck', 'confirmed', 'paid', 'tosupplier', 'awaitingship', 'shipped', 'intransit', 'onhold']
ORDER_FIELD_NAMES_KEYS = {'order_text': 'field_name_order_text', 'full_name': 'field_name_full_name', 'delivery_address': 'field_name_delivery_address', 'payment_method': 'field_name_payment_method', 'contact_phone': 'field_name_contact_phone', 'delivery_notes': 'field_name_delivery_notes'}
PHONE_NUMBER_REGEX = re.compile(r"^\+?\d{10,12}$")
ORDER_FIELDS_CONFIG = [
    {"key": "order_text", "prompt_key": "prompt_order_text", "state_name": "waiting_for_order_text", "next_field": "full_name", "input_type": "text"},
    {"key": "full_name", "prompt_key": "prompt_full_name", "state_name": "waiting_for_full_name", "next_field": "delivery_address", "input_type": "text"},
    {"key": "delivery_address", "prompt_key": "prompt_delivery_address", "state_name": "waiting_for_delivery_address", "next_field": "payment_method", "input_type": "text"},
    {"key": "payment_method", "prompt_key": "prompt_payment_method", "state_name": "waiting_for_payment_method", "next_field": "contact_phone", "input_type": "buttons", "options_keys": {"button_payment_cash": "cash", "button_payment_card_on_delivery": "card_on_delivery"}},
    {"key": "contact_phone", "prompt_key": "prompt_contact_phone", "state_name": "waiting_for_contact_phone", "next_field": "delivery_notes", "input_type": "contact_button"},
    {"key": "delivery_notes", "prompt_key": "prompt_delivery_notes", "state_name": "waiting_for_delivery_notes", "next_field": "final_confirm", "input_type": "text"}
]
ORDER_FIELD_MAP = {field["key"]: field for field in ORDER_FIELDS_CONFIG}
