"""Help message handler - uses HelpMessageService."""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.enums import ParseMode

from core.database import get_db_session
from repositories.help_messages import HelpMessageRepository
from services.help_message_service import HelpMessageService
from bot.keyboards.user_keyboards import back_to_main_menu_kb
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "get_help")
async def get_help(callback: CallbackQuery, lang: str):
    """Show active help message or fallback text."""
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested help")

    async with get_db_session() as session:
        help_repo = HelpMessageRepository(session)
        help_service = HelpMessageService(help_repo)
        active_msg = await help_service.get_active_help_message(lang)

    text = active_msg.message_text if active_msg else get_localized_message("help_message_not_configured", lang)
    kb = back_to_main_menu_kb(lang)

    await callback.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await callback.answer()

