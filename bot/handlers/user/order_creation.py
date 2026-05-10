"""Order creation FSM handlers - slimmed down using OrderService.

Original: 517 lines mixing FSM, validation, DB, and string formatting.
Refactored: ~170 lines, handlers only do I/O, business logic in OrderService.
"""
import logging
import html
from typing import Union

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode

from core.database import get_db_session
from core.config import ORDER_FIELDS_CONFIG, ORDER_FIELD_MAP, ORDER_FIELD_NAMES_KEYS, settings
from core.exceptions import InvalidPhoneError, OrderValidationError
from repositories.orders import OrderRepository
from repositories.users import UserRepository
from services.order_service import OrderService, OrderCreateData
from services.notification_service import NotificationService
from bot.states.order_states import OrderStates
from bot.keyboards.user_keyboards import (
    main_menu_kb, confirm_cancel_kb, final_confirm_order_kb,
    payment_method_kb, phone_contact_kb,
)
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


# ─── helpers ────────────────────────────────────────────────────────────────

async def _send_field_prompt(
    update: Union[Message, CallbackQuery],
    state: FSMContext,
    lang: str,
    next_field_key: str,
) -> None:
    """Advance FSM to next field and send appropriate prompt."""
    if next_field_key == "final_confirm":
        await _show_order_summary(update, state, lang)
        return

    cfg = ORDER_FIELD_MAP.get(next_field_key)
    if not cfg:
        logger.error(f"Unknown field key: {next_field_key}")
        await _go_to_main_menu(update, state, lang)
        return

    await state.set_state(getattr(OrderStates, cfg["state_name"]))
    await state.update_data(current_field_key=cfg["key"])
    prompt = get_localized_message(cfg["prompt_key"], lang)

    if cfg["input_type"] == "buttons":
        kb = payment_method_kb(lang, cfg["options_keys"])
        if isinstance(update, CallbackQuery):
            await update.message.edit_text(prompt, reply_markup=kb, parse_mode=ParseMode.HTML)
            await update.answer()
        else:
            await update.answer(prompt, reply_markup=kb, parse_mode=ParseMode.HTML)

    elif cfg["input_type"] == "contact_button":
        kb = phone_contact_kb(lang)
        if isinstance(update, CallbackQuery):
            await update.message.delete()
            await update.message.answer(prompt, reply_markup=kb, parse_mode=ParseMode.HTML)
            await update.answer()
        else:
            await update.answer(prompt, reply_markup=kb, parse_mode=ParseMode.HTML)

    else:  # text
        remove_kb = ReplyKeyboardRemove()
        if isinstance(update, CallbackQuery):
            await update.message.delete()
            await update.message.answer(prompt, reply_markup=remove_kb, parse_mode=ParseMode.HTML)
            await update.answer()
        else:
            await update.answer(prompt, reply_markup=remove_kb, parse_mode=ParseMode.HTML)


async def _show_order_summary(
    update: Union[Message, CallbackQuery],
    state: FSMContext,
    lang: str,
) -> None:
    """Build and display the final order summary with confirm/cancel buttons."""
    await state.set_state(OrderStates.confirm_order)
    user_data = await state.get_data()

    summary = get_localized_message("final_order_summary_title", lang) + "\n\n"
    for field_cfg in ORDER_FIELDS_CONFIG:
        key = field_cfg["key"]
        value = user_data.get(key)
        field_name = get_localized_message(ORDER_FIELD_NAMES_KEYS.get(key, key), lang)

        if key == "payment_method" and value:
            opts = ORDER_FIELD_MAP.get("payment_method", {}).get("options_keys", {})
            loc_key = next((k for k, v in opts.items() if v == value), None)
            if loc_key:
                value = get_localized_message(loc_key, lang)

        no_notes = get_localized_message("no_notes_display", lang)
        if key == "delivery_notes" and (
            value is None or str(value).strip() in ["-", get_localized_message("no_notes_keyword", lang).lower()]
        ):
            value = no_notes

        escaped = html.escape(str(value)) if value is not None else get_localized_message("not_specified", lang)
        if key == "order_text":
            summary += f"<b>{field_name.capitalize()}</b>:\n<code>{escaped}</code>\n"
        else:
            summary += f"<b>{field_name.capitalize()}</b>: {escaped}\n"

    summary += "\n" + get_localized_message("final_order_summary_confirmation", lang)
    kb = final_confirm_order_kb(lang)

    if isinstance(update, Message):
        await update.answer(summary, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.message.edit_text(summary, reply_markup=kb, parse_mode=ParseMode.HTML)
        await update.answer()


async def _go_to_main_menu(update: Union[Message, CallbackQuery], state: FSMContext, lang: str) -> None:
    """Clear state and return to main menu."""
    await state.clear()
    kb = main_menu_kb(lang)
    text = get_localized_message("welcome", lang)
    if isinstance(update, Message):
        await update.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    else:
        await update.answer()
        await update.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)


# ─── start order ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "make_order")
async def make_order_callback(callback: CallbackQuery, state: FSMContext, lang: str):
    """Begin order creation flow."""
    logger.info(f"User {callback.from_user.id} started order creation")
    await _send_field_prompt(callback, state, lang, ORDER_FIELDS_CONFIG[0]["key"])
    await callback.answer()


# ─── field input handlers ────────────────────────────────────────────────────

@router.message(OrderStates.waiting_for_order_text)
async def process_order_text(message: Message, state: FSMContext, lang: str):
    text = message.text.strip()
    if not text:
        await message.answer(get_localized_message("prompt_order_text", lang))
        return
    await state.update_data(order_text=text)
    confirm_text = get_localized_message("prompt_order_text_confirmation", lang).format(order_text=html.escape(text))
    await message.answer(confirm_text, reply_markup=confirm_cancel_kb(lang, "confirm_field_input:order_text"), parse_mode=ParseMode.HTML)


@router.message(OrderStates.waiting_for_full_name)
async def process_full_name(message: Message, state: FSMContext, lang: str):
    name = message.text.strip()
    if not name:
        await message.answer(get_localized_message("prompt_full_name", lang))
        return
    await state.update_data(full_name=name)
    confirm_text = get_localized_message("prompt_full_name_confirmation", lang).format(full_name=html.escape(name))
    await message.answer(confirm_text, reply_markup=confirm_cancel_kb(lang, "confirm_field_input:full_name"), parse_mode=ParseMode.HTML)


@router.message(OrderStates.waiting_for_delivery_address)
async def process_delivery_address(message: Message, state: FSMContext, lang: str):
    addr = message.text.strip()
    if not addr:
        await message.answer(get_localized_message("prompt_delivery_address", lang))
        return
    await state.update_data(delivery_address=addr)
    confirm_text = get_localized_message("prompt_delivery_address_confirmation", lang).format(delivery_address=html.escape(addr))
    await message.answer(confirm_text, reply_markup=confirm_cancel_kb(lang, "confirm_field_input:delivery_address"), parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("set_field_payment_method_"))
async def process_payment_method(callback: CallbackQuery, state: FSMContext, lang: str):
    method = callback.data.split("_")[-1]
    await state.update_data(payment_method=method)

    opts = ORDER_FIELD_MAP.get("payment_method", {}).get("options_keys", {})
    loc_key = next((k for k, v in opts.items() if v == method), None)
    display = get_localized_message(loc_key, lang) if loc_key else method

    confirm_text = get_localized_message("prompt_payment_method_confirmation", lang).format(payment_method=html.escape(display))
    await callback.message.edit_text(confirm_text, reply_markup=confirm_cancel_kb(lang, "confirm_field_input:payment_method"), parse_mode=ParseMode.HTML)
    await callback.answer()


@router.message(OrderStates.waiting_for_contact_phone)
async def process_contact_phone(message: Message, state: FSMContext, lang: str):
    from core.config import PHONE_NUMBER_REGEX
    phone = None

    if message.contact:
        phone = message.contact.phone_number
        await message.answer(get_localized_message("thank_you_processing", lang), reply_markup=ReplyKeyboardRemove())
    elif message.text:
        raw = message.text.strip()
        if PHONE_NUMBER_REGEX.fullmatch(raw):
            phone = raw
        else:
            await message.answer(get_localized_message("error_invalid_phone_format", lang), parse_mode=ParseMode.HTML)
            return

    if not phone:
        await message.answer(get_localized_message("prompt_contact_phone", lang))
        return

    await state.update_data(contact_phone=phone)
    confirm_text = get_localized_message("prompt_contact_phone_confirmation", lang).format(phone_number=html.escape(phone))
    await message.answer(confirm_text, reply_markup=confirm_cancel_kb(lang, "confirm_field_input:contact_phone"), parse_mode=ParseMode.HTML)


@router.message(OrderStates.waiting_for_delivery_notes)
async def process_delivery_notes(message: Message, state: FSMContext, lang: str):
    notes = message.text.strip()
    no_notes_kw = get_localized_message("no_notes_keyword", lang).lower()
    if notes.lower() in ["-", no_notes_kw]:
        notes = get_localized_message("no_notes_display", lang)
    await state.update_data(delivery_notes=notes)
    confirm_text = get_localized_message("prompt_delivery_notes_confirmation", lang).format(delivery_notes=html.escape(notes))
    await message.answer(confirm_text, reply_markup=confirm_cancel_kb(lang, "confirm_field_input:delivery_notes"), parse_mode=ParseMode.HTML)


# ─── field confirmation ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("confirm_field_input:"))
async def confirm_field_input(callback: CallbackQuery, state: FSMContext, lang: str):
    """Move FSM to the next field after user confirms current field."""
    confirmed_key = callback.data.split(":")[1]
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer(get_localized_message("thank_you_processing", lang))

    cfg = ORDER_FIELD_MAP.get(confirmed_key)
    if not cfg:
        logger.error(f"Unknown confirmed field: {confirmed_key}")
        await _go_to_main_menu(callback, state, lang)
        return

    await _send_field_prompt(callback, state, lang, cfg.get("next_field"))


# ─── final confirmation ────────────────────────────────────────────────────────

@router.callback_query(F.data == "final_confirm_order")
async def final_confirm_order(callback: CallbackQuery, state: FSMContext, bot: Bot, lang: str):
    """Save order to DB, notify admins and user, then return to menu."""
    user_data = await state.get_data()
    user_id = callback.from_user.id
    logger.info(f"User {user_id} confirmed final order submission")

    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        user_repo = UserRepository(session)
        order_service = OrderService(order_repo, user_repo)

        # Ensure user exists and get username
        user = await user_repo.get_or_create(
            user_id=user_id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            last_name=callback.from_user.last_name,
        )

        try:
            order = await order_service.create_order(OrderCreateData(
                user_id=user_id,
                username=user.username or "unknown",
                order_text=user_data.get("order_text", get_localized_message("not_specified", lang)),
                full_name=user_data.get("full_name"),
                delivery_address=user_data.get("delivery_address"),
                payment_method=user_data.get("payment_method"),
                contact_phone=user_data.get("contact_phone"),
                delivery_notes=user_data.get("delivery_notes"),
            ))
        except (InvalidPhoneError, OrderValidationError) as e:
            logger.error(f"Order creation failed for user {user_id}: {e}")
            await callback.message.edit_text(
                get_localized_message("error_order_processing", lang), parse_mode=ParseMode.HTML
            )
            await state.clear()
            await callback.answer()
            return

        # Notify admins
        notif_service = NotificationService(bot, order_repo, user_repo)
        await notif_service.notify_admins_new_order(order.id, settings.admin_ids)
        await notif_service.notify_user_order_placed(user_id, order.id, lang)

    await callback.message.edit_text(
        get_localized_message("order_placed_success", lang).format(order_id=order.id),
        parse_mode=ParseMode.HTML,
    )
    await state.clear()
    await _go_to_main_menu(callback, state, lang)
    await callback.answer()


# ─── cancel ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext, lang: str):
    """Cancel order creation at any step."""
    logger.info(f"User {callback.from_user.id} cancelled order")
    await state.clear()
    await callback.message.edit_text(get_localized_message("order_cancelled_success", lang))
    await _go_to_main_menu(callback, state, lang)
    await callback.answer()

