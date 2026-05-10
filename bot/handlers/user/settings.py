"""Language and notification settings handlers - extracted from user_utils.py."""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.enums import ParseMode

from core.database import get_db_session
from repositories.users import UserRepository
from bot.keyboards.user_keyboards import language_kb, notification_settings_kb, back_to_main_menu_kb
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "show_language_options")
async def show_language_options(callback: CallbackQuery, lang: str):
    """Show language selection menu."""
    await callback.message.edit_text(
        get_localized_message("choose_language_prompt", lang),
        reply_markup=language_kb(lang),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_lang_"))
async def change_language(callback: CallbackQuery, lang: str):
    """Handle language selection."""
    user_id = callback.from_user.id
    new_lang = callback.data.split("_")[2]

    async with get_db_session() as session:
        user_repo = UserRepository(session)
        updated = await user_repo.update_language(user_id, new_lang)

    kb = back_to_main_menu_kb(new_lang)
    if updated:
        text = get_localized_message("language_changed_success_alert", new_lang).format(new_lang=new_lang.upper())
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        text = get_localized_message("language_change_failed_alert", lang)
        await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data == "show_notification_settings")
async def show_notification_settings(callback: CallbackQuery, lang: str):
    """Show notification settings menu."""
    user_id = callback.from_user.id

    async with get_db_session() as session:
        user_repo = UserRepository(session)
        is_enabled = await user_repo.get_notifications_enabled(user_id)

    status_key = "notifications_enabled_status" if is_enabled else "notifications_disabled_status"
    emoji = "✅" if is_enabled else "❌"
    text = get_localized_message("notification_settings_title", lang).format(
        current_status=get_localized_message(status_key, lang),
        status_emoji=emoji,
    )

    await callback.message.edit_text(
        text,
        reply_markup=notification_settings_kb(lang, is_enabled),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_notifications_"))
async def toggle_notifications(callback: CallbackQuery, lang: str):
    """Toggle notification status on/off."""
    user_id = callback.from_user.id
    action = callback.data.split("_")[-1]  # 'on' or 'off'
    new_status = action == "on"

    async with get_db_session() as session:
        user_repo = UserRepository(session)
        updated = await user_repo.update_notifications(user_id, new_status)

    if updated:
        alert_key = "notifications_enabled_alert" if new_status else "notifications_disabled_alert"
        await callback.answer(get_localized_message(alert_key, lang), show_alert=True)
        # Refresh the notification settings menu
        is_enabled = await _get_notifications_status(user_id)
        status_key = "notifications_enabled_status" if is_enabled else "notifications_disabled_status"
        emoji = "✅" if is_enabled else "❌"
        text = get_localized_message("notification_settings_title", lang).format(
            current_status=get_localized_message(status_key, lang),
            status_emoji=emoji,
        )
        await callback.message.edit_text(
            text,
            reply_markup=notification_settings_kb(lang, is_enabled),
            parse_mode=ParseMode.HTML,
        )
    else:
        await callback.answer(get_localized_message("notifications_toggle_failed_alert", lang), show_alert=True)


async def _get_notifications_status(user_id: int) -> bool:
    """Get current notifications status for user."""
    async with get_db_session() as session:
        user_repo = UserRepository(session)
        status = await user_repo.get_notifications_enabled(user_id)
        return status if status is not None else True

