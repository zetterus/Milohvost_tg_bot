import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.utils.markdown import hbold

from models import Order, HelpMessage
from db import get_active_help_message_from_db
from .admin_filters import IsAdmin
from .admin_states import AdminStates

logger = logging.getLogger(__name__)
router = Router()  # Локальный роутер для этого модуля


@router.callback_query(F.data == "admin_manage_help_messages", IsAdmin())
async def admin_manage_help_messages_callback(callback: CallbackQuery):
    """
    Показывает меню управления сообщениями помощи.
    """
    logger.info(f"Админ {callback.from_user.id} вошел в управление сообщениями помощи.")

    keyboard = InlineKeyboardBuilder()
    # Добавьте кнопки для создания, редактирования, просмотра, активации/деактивации сообщений помощи
    keyboard.row(
        InlineKeyboardButton(text="Просмотреть текущее сообщение помощи", callback_data="admin_view_help_message"))
    keyboard.row(InlineKeyboardButton(text="Создать/Редактировать сообщение помощи",
                                      callback_data="admin_edit_help_message"))
    # Добавьте другие кнопки, если нужны (например, история версий, удаление)
    keyboard.row(InlineKeyboardButton(text="🔙 В админ-панель", callback_data="admin_panel_back"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        hbold("Меню управления сообщениями помощи:"),
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_view_help_message", IsAdmin())
async def admin_view_help_message_callback(callback: CallbackQuery):
    """
    Отображает текущее активное сообщение помощи.
    """
    active_message = await get_active_help_message_from_db()

    if active_message:
        text_to_display = (
            f"{hbold('Текущее активное сообщение помощи:')}\n\n"
            f"{active_message.text}\n\n"
            f"{hbold('Статус:')} {'Активно ✅' if active_message.is_active else 'Неактивно ❌'}\n"
            f"{hbold('Дата создания:')} {active_message.created_at.strftime('%d.%m.%Y %H:%M:%S')}"
        )
    else:
        text_to_display = hbold("Активное сообщение помощи не найдено.")

    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(text="🔙 К управлению помощью", callback_data="admin_manage_help_messages"))

    await callback.message.edit_text(
        text_to_display,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()
