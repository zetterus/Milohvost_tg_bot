"""User-facing keyboard builders."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder
from localization import get_localized_message
def main_menu_kb(lang: str) -> InlineKeyboardMarkup:
    """Main user menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_localized_message("button_make_order", lang), callback_data="make_order")
    builder.button(text=get_localized_message("button_view_my_orders", lang), callback_data="view_my_orders")
    builder.button(text=get_localized_message("button_get_help", lang), callback_data="get_help")
    builder.button(text=get_localized_message("button_my_language", lang), callback_data="show_language_options")
    builder.button(text=get_localized_message("button_notification_settings", lang), callback_data="show_notification_settings")
    builder.adjust(1)
    return builder.as_markup()
def back_to_main_menu_kb(lang: str) -> InlineKeyboardMarkup:
    """Single back-to-main-menu button."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang), callback_data="user_main_menu_back"))
    return builder.as_markup()
def confirm_cancel_kb(lang: str, confirm_data: str) -> InlineKeyboardMarkup:
    """Confirm + Cancel inline keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang), callback_data=confirm_data))
    builder.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    return builder.as_markup()
def final_confirm_order_kb(lang: str) -> InlineKeyboardMarkup:
    """Final order confirmation keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_localized_message("button_confirm", lang), callback_data="final_confirm_order"))
    builder.row(InlineKeyboardButton(text=get_localized_message("button_cancel", lang), callback_data="cancel_order"))
    builder.adjust(1)
    return builder.as_markup()
def payment_method_kb(lang: str, options_keys: dict) -> InlineKeyboardMarkup:
    """Payment method selection keyboard."""
    builder = InlineKeyboardBuilder()
    for option_key, option_value in options_keys.items():
        builder.button(text=get_localized_message(option_key, lang), callback_data=f"set_field_payment_method_{option_value}")
    builder.adjust(1)
    return builder.as_markup()
def phone_contact_kb(lang: str) -> ReplyKeyboardMarkup:
    """Share phone contact keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_localized_message("button_send_phone_number", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
def language_kb(lang: str) -> InlineKeyboardMarkup:
    """Language selection keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇺🇦 Українська", callback_data="set_lang_uk")
    builder.button(text="🇬🇧 English", callback_data="set_lang_en")
    builder.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    builder.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang), callback_data="user_main_menu_back"))
    builder.adjust(1)
    return builder.as_markup()
def notification_settings_kb(lang: str, is_enabled: bool) -> InlineKeyboardMarkup:
    """Notification settings keyboard."""
    builder = InlineKeyboardBuilder()
    if is_enabled:
        builder.button(text=get_localized_message("button_disable_notifications", lang), callback_data="toggle_notifications_off")
    else:
        builder.button(text=get_localized_message("button_enable_notifications", lang), callback_data="toggle_notifications_on")
    builder.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang), callback_data="user_main_menu_back"))
    builder.adjust(1)
    return builder.as_markup()
