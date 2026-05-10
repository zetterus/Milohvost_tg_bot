"""Admin help messages management - uses HelpMessageService."""
import logging
import html
from typing import Union

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter

from core.database import get_db_session
from repositories.help_messages import HelpMessageRepository
from services.help_message_service import HelpMessageService
from bot.handlers.admin.filters import IsAdmin
from bot.states.admin_states import AdminStates
from localization import get_localized_message, get_available_languages

logger = logging.getLogger(__name__)
router = Router()


async def _show_help_menu(update: Union[Message, CallbackQuery], state: FSMContext, lang: str) -> None:
    """Show help messages management menu."""
    available_langs = get_available_languages()
    status_parts = []

    async with get_db_session() as session:
        help_service = HelpMessageService(HelpMessageRepository(session))
        for lc in available_langs:
            active = await help_service.get_active_help_message(lc)
            if active:
                status_parts.append(get_localized_message("admin_help_active_message_status_lang", lang).format(
                    lang_code=lc.upper(), message_id=active.id))
            else:
                status_parts.append(get_localized_message("admin_help_no_active_message_lang", lang).format(lang_code=lc.upper()))

    title = get_localized_message("admin_help_manage_title", lang).format(current_active_status="\n".join(status_parts))
    kb = InlineKeyboardBuilder()
    kb.button(text=get_localized_message("admin_button_create_help_message", lang), callback_data="admin_create_help_message")
    kb.button(text=get_localized_message("admin_button_manage_existing_help_messages", lang), callback_data="admin_view_all_help_messages")
    kb.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang), callback_data="admin_panel_back"))
    kb.adjust(1)

    if isinstance(update, Message):
        await update.answer(title, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await update.message.edit_text(title, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        await update.answer()


async def _show_help_message_detail(
    update: Union[Message, CallbackQuery], state: FSMContext, message_id: int, lang: str
) -> None:
    """Show details of a specific help message."""
    async with get_db_session() as session:
        msg_obj = await HelpMessageRepository(session).get_by_id(message_id)

    if not msg_obj:
        err = get_localized_message("admin_help_message_not_found", lang).format(message_id=message_id)
        if isinstance(update, CallbackQuery):
            await update.answer(err, show_alert=True)
        await _show_help_menu(update, state, lang)
        return

    status_emoji = "✅" if msg_obj.is_active else "❌"
    status_text = get_localized_message("admin_help_status_active" if msg_obj.is_active else "admin_help_status_inactive", lang)

    details = get_localized_message("admin_help_message_details_title", lang) + "\n\n"
    details += f"<b>{get_localized_message('admin_help_message_id_label', lang)}</b>: <code>{msg_obj.id}</code>\n"
    details += f"<b>{get_localized_message('admin_help_message_language_label', lang)}</b>: {msg_obj.language_code.upper()}\n"
    details += f"<b>{get_localized_message('admin_help_message_status_label', lang)}</b>: {status_emoji} {status_text} {status_emoji}\n"
    details += f"<b>{get_localized_message('field_name_order_text', lang)}</b>:\n<code>{html.escape(msg_obj.message_text)}</code>\n\n"
    details += f"<b>{get_localized_message('admin_help_message_created_at_label', lang)}</b>: {msg_obj.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    details += f"<b>{get_localized_message('admin_help_message_updated_at_label', lang)}</b>: {msg_obj.updated_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    details += get_localized_message("admin_help_what_to_do", lang)

    kb = InlineKeyboardBuilder()
    lang_buttons = []
    for lc in get_available_languages():
        btn_text = get_localized_message(f"admin_button_lang_{lc}", lang)
        if lc == msg_obj.language_code:
            btn_text = f"✅ {btn_text}"
        lang_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=f"admin_set_help_msg_lang:{msg_obj.id}:{lc}"))
    kb.row(*lang_buttons)

    if msg_obj.is_active:
        kb.row(InlineKeyboardButton(text=get_localized_message("admin_button_deactivate_help_message", lang), callback_data=f"admin_deactivate_help_message:{message_id}"))
    else:
        kb.row(InlineKeyboardButton(text=get_localized_message("admin_button_activate_help_message", lang), callback_data=f"admin_activate_help_message:{message_id}"))

    kb.row(InlineKeyboardButton(text=get_localized_message("admin_button_delete", lang), callback_data=f"admin_confirm_delete_help_message:{message_id}"))
    kb.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_messages_list", lang), callback_data="admin_view_all_help_messages"))
    kb.adjust(1)

    if isinstance(update, Message):
        await update.answer(details, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await update.message.edit_text(details, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        await update.answer()


@router.callback_query(F.data == "admin_manage_help_messages", IsAdmin())
async def manage_help_messages(callback: CallbackQuery, state: FSMContext, lang: str):
    await _show_help_menu(callback, state, lang)


@router.callback_query(F.data == "admin_create_help_message", IsAdmin())
async def create_help_message_start(callback: CallbackQuery, state: FSMContext, lang: str):
    await state.set_state(AdminStates.waiting_for_help_message_text)
    await callback.message.edit_text(get_localized_message("admin_help_prompt_new_message_text", lang), parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(AdminStates.waiting_for_help_message_text, IsAdmin())
async def process_new_help_message(message: Message, state: FSMContext, lang: str):
    text = message.text.strip()
    if not text:
        await message.answer(get_localized_message("admin_help_empty_message_error", lang))
        return

    await state.update_data(new_help_message_text=text)
    preview = html.escape(text[:200]) + ("..." if len(text) > 200 else "")
    preview_text = get_localized_message("admin_help_preview_title", lang) + "\n\n" + preview + "\n\n" + get_localized_message("admin_help_what_to_do", lang)

    kb = InlineKeyboardBuilder()
    kb.button(text=get_localized_message("admin_button_save_and_activate", lang), callback_data="admin_save_help_message:activate")
    kb.button(text=get_localized_message("admin_button_save_only", lang), callback_data="admin_save_help_message:no_activate")
    kb.row(InlineKeyboardButton(text=get_localized_message("admin_button_cancel_creation", lang), callback_data="admin_cancel_help_message_creation"))
    kb.adjust(1)
    await message.answer(preview_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("admin_save_help_message:"), IsAdmin())
async def save_help_message(callback: CallbackQuery, state: FSMContext, lang: str):
    data = await state.get_data()
    msg_text = data.get("new_help_message_text")
    action = callback.data.split(":")[1]

    if not msg_text:
        await callback.answer(get_localized_message("admin_help_error_text_not_found", lang), show_alert=True)
        await state.clear()
        await _show_help_menu(callback, state, lang)
        return

    if action == "activate":
        await state.update_data(temp_message_text=msg_text)
        await state.set_state(AdminStates.waiting_for_help_message_selection)
        kb = InlineKeyboardBuilder()
        for lc in get_available_languages():
            kb.button(text=get_localized_message(f"admin_button_lang_{lc}", lang), callback_data=f"admin_add_help_msg_with_lang:{lc}")
        kb.adjust(2)
        kb.row(InlineKeyboardButton(text=get_localized_message("admin_button_cancel_creation", lang), callback_data="admin_cancel_help_message_creation"))
        await callback.message.edit_text(get_localized_message("admin_help_prompt_activate_language", lang), reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    async with get_db_session() as session:
        new_msg = await HelpMessageRepository(session).create(msg_text, lang, is_active=False)

    if new_msg:
        alert = get_localized_message("admin_help_saved_only", lang).format(message_id=new_msg.id)
        await callback.answer(alert, show_alert=True)
        await callback.message.edit_text(alert, parse_mode=ParseMode.HTML)
    else:
        await callback.answer(get_localized_message("error_order_processing", lang), show_alert=True)

    await state.clear()
    await _show_help_menu(callback, state, lang)


@router.callback_query(
    F.data.startswith("admin_add_help_msg_with_lang:"),
    IsAdmin(),
    StateFilter(AdminStates.waiting_for_help_message_selection)
)
async def save_help_message_with_lang(callback: CallbackQuery, state: FSMContext, lang: str):
    data = await state.get_data()
    msg_text = data.get("temp_message_text")
    selected_lang = callback.data.split(":")[1]

    if not msg_text:
        await callback.answer(get_localized_message("admin_help_error_text_not_found", lang), show_alert=True)
        await state.clear()
        await _show_help_menu(callback, state, lang)
        return

    async with get_db_session() as session:
        new_msg = await HelpMessageRepository(session).create(msg_text, selected_lang, is_active=True)

    if new_msg:
        alert = get_localized_message("admin_help_saved_and_activated", lang).format(message_id=new_msg.id)
        await callback.answer(alert, show_alert=True)
        await callback.message.edit_text(alert, parse_mode=ParseMode.HTML)
    else:
        await callback.answer(get_localized_message("error_order_processing", lang), show_alert=True)

    await state.clear()
    await _show_help_menu(callback, state, lang)


@router.callback_query(F.data == "admin_cancel_help_message_creation", IsAdmin())
async def cancel_help_creation(callback: CallbackQuery, state: FSMContext, lang: str):
    await state.clear()
    await callback.answer(get_localized_message("admin_help_creation_cancelled", lang), show_alert=True)
    await _show_help_menu(callback, state, lang)


@router.callback_query(F.data == "admin_view_all_help_messages", IsAdmin())
async def view_all_help_messages(callback: CallbackQuery, state: FSMContext, lang: str):
    async with get_db_session() as session:
        all_msgs = await HelpMessageRepository(session).get_all()

    text = get_localized_message("admin_help_all_messages_title", lang) + "\n\n"
    if not all_msgs:
        text += get_localized_message("admin_help_no_saved_messages", lang)
    else:
        for msg in all_msgs:
            emoji = "✅" if msg.is_active else "❌"
            preview = html.escape(msg.message_text[:50]) + ("..." if len(msg.message_text) > 50 else "")
            text += get_localized_message("admin_help_message_entry", lang).format(
                status_emoji=emoji, message_id=msg.id, preview_text=preview,
                created_at=msg.created_at.strftime("%d.%m.%Y %H:%M")
            ) + "\n"

    kb = InlineKeyboardBuilder()
    if all_msgs:
        for msg in all_msgs:
            kb.row(InlineKeyboardButton(
                text=get_localized_message("admin_help_button_select", lang).format(message_id=msg.id),
                callback_data=f"admin_show_help_message_details:{msg.id}"
            ))
    kb.row(InlineKeyboardButton(text=get_localized_message("admin_button_back_to_help_management", lang), callback_data="admin_manage_help_messages"))
    kb.adjust(1)

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
    await callback.answer()


@router.callback_query(F.data.startswith("admin_show_help_message_details:"), IsAdmin())
async def show_help_message_details(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    await _show_help_message_detail(callback, state, message_id, lang)


@router.callback_query(F.data.startswith("admin_activate_help_message:"), IsAdmin())
async def activate_help_message(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    async with get_db_session() as session:
        repo = HelpMessageRepository(session)
        msg_obj = await repo.get_by_id(message_id)
        if not msg_obj:
            await callback.answer(get_localized_message("admin_help_activate_failed", lang).format(message_id=message_id), show_alert=True)
            return
        success = await repo.set_active(message_id, msg_obj.language_code)

    if success:
        await callback.answer(get_localized_message("admin_help_activated_success", lang).format(message_id=message_id), show_alert=True)
        await _show_help_message_detail(callback, state, message_id, lang)
    else:
        await callback.answer(get_localized_message("admin_help_activate_failed", lang).format(message_id=message_id), show_alert=True)


@router.callback_query(F.data.startswith("admin_deactivate_help_message:"), IsAdmin())
async def deactivate_help_message(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    async with get_db_session() as session:
        success = await HelpMessageRepository(session).deactivate(message_id)

    if success:
        await callback.answer(get_localized_message("admin_help_deactivated_success", lang).format(message_id=message_id), show_alert=True)
        await _show_help_message_detail(callback, state, message_id, lang)
    else:
        await callback.answer(get_localized_message("admin_help_deactivate_failed", lang).format(message_id=message_id), show_alert=True)


@router.callback_query(F.data.startswith("admin_confirm_delete_help_message:"), IsAdmin())
async def confirm_delete_help_message(callback: CallbackQuery, lang: str):
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(text=get_localized_message("button_yes_delete", lang), callback_data=f"admin_delete_help_message:{message_id}")
    kb.button(text=get_localized_message("button_no_cancel", lang), callback_data=f"admin_show_help_message_details:{message_id}")
    kb.adjust(2)
    await callback.message.edit_text(
        get_localized_message("admin_confirm_delete_help_message_prompt", lang).format(message_id=message_id),
        reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_help_message:"), IsAdmin())
async def delete_help_message_confirmed(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        message_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    async with get_db_session() as session:
        success = await HelpMessageRepository(session).delete(message_id)

    if success:
        alert = get_localized_message("admin_help_deleted_success", lang).format(message_id=message_id)
    else:
        alert = get_localized_message("admin_help_delete_failed", lang).format(message_id=message_id)

    await callback.answer(alert, show_alert=True)
    await callback.message.edit_text(alert, parse_mode=ParseMode.HTML)
    await _show_help_menu(callback, state, lang)


@router.callback_query(F.data.startswith("admin_set_help_msg_lang:"), IsAdmin())
async def set_help_message_language(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        parts = callback.data.split(":")
        message_id = int(parts[1])
        new_lang = parts[2]
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    async with get_db_session() as session:
        updated = await HelpMessageRepository(session).update(message_id, language_code=new_lang)

    if updated:
        alert = get_localized_message("admin_help_language_changed_success", lang).format(message_id=message_id, new_lang=new_lang.upper())
        await callback.answer(alert, show_alert=True)
    else:
        await callback.answer(get_localized_message("admin_help_language_change_failed", lang).format(message_id=message_id), show_alert=True)

    await _show_help_message_detail(callback, state, message_id, lang)

