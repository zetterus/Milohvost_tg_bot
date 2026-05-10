"""User start and main menu handlers."""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.enums import ParseMode

from core.database import get_db_session
from repositories.users import UserRepository
from bot.keyboards.user_keyboards import main_menu_kb
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


async def show_main_menu(update_object: Message | CallbackQuery, lang: str) -> None:
    """Display the main menu to the user."""
    menu_text = get_localized_message("welcome", lang)
    kb = main_menu_kb(lang)

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=kb, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(menu_text, reply_markup=kb, parse_mode=ParseMode.HTML)


@router.message(Command("start"))
async def start_command(message: Message, state: FSMContext, lang: str):
    """Handle /start command - register user and show main menu."""
    logger.info(f"User {message.from_user.id} sent /start")

    async with get_db_session() as session:
        user_repo = UserRepository(session)
        await user_repo.get_or_create(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
        )

    await state.clear()
    await show_main_menu(message, lang)


@router.callback_query(F.data == "user_main_menu_back")
async def main_menu_back(callback: CallbackQuery, state: FSMContext, lang: str):
    """Return to main menu from any submenu."""
    logger.info(f"User {callback.from_user.id} returned to main menu")

    async with get_db_session() as session:
        user_repo = UserRepository(session)
        await user_repo.get_or_create(
            user_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

    await state.clear()
    await show_main_menu(callback, lang)

