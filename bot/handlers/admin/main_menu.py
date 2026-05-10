"""Admin main menu handler - using settings instead of old config."""
import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from core.database import get_db_session
from repositories.users import UserRepository
from bot.keyboards.admin_keyboards import admin_main_menu_kb
from bot.handlers.admin.filters import IsAdmin
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


async def show_admin_menu(update: Message | CallbackQuery, state: FSMContext, lang: str) -> None:
    """Display admin panel main menu."""
    await state.clear()
    text = get_localized_message("admin_welcome_message", lang)
    kb = admin_main_menu_kb(lang)

    if isinstance(update, Message):
        await update.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.answer()
        await update.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(Command("admin"), IsAdmin())
async def admin_command(message: Message, state: FSMContext, lang: str):
    """Handle /admin command."""
    logger.info(f"Admin {message.from_user.id} opened admin panel")
    async with get_db_session() as session:
        await UserRepository(session).get_or_create(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )
    await show_admin_menu(message, state, lang)


@router.callback_query(F.data == "admin_panel_back", IsAdmin())
async def admin_panel_back(callback: CallbackQuery, state: FSMContext, lang: str):
    """Return to admin main menu."""
    await show_admin_menu(callback, state, lang)

