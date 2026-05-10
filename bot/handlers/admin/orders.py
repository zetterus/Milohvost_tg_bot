"""Admin orders management handlers."""
import logging
import html
import math
import urllib.parse
from typing import Union

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.filters import StateFilter

from core.database import get_db_session
from core.config import settings, ORDER_STATUS_KEYS, ORDER_FIELD_NAMES_KEYS, ORDER_FIELD_MAP
from repositories.orders import OrderRepository
from services.order_service import OrderService
from bot.handlers.admin.filters import IsAdmin
from bot.states.admin_states import AdminStates
from bot.handlers.admin.main_menu import show_admin_menu
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()

LIMIT = settings.orders_per_page
MAX_PREV = settings.max_preview_text_length


# ─── helpers ───────────────────────────────────────────────────────────────

async def _show_order_list(
    update: Union[Message, CallbackQuery],
    state: FSMContext,
    lang: str,
    page: int,
    is_search: bool = False,
) -> None:
    """Shared logic for showing paginated order list."""
    offset = (page - 1) * LIMIT

    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        if is_search:
            data = await state.get_data()
            query = data.get("search_query", "")
            if not query:
                await _alert(update, get_localized_message("error_search_query_not_found", lang))
                await show_admin_menu(update, state, lang)
                return
            orders, total = await order_repo.search(query, offset=offset, limit=LIMIT)
        else:
            query = None
            orders, total = await order_repo.get_all(offset=offset, limit=LIMIT)

    await state.update_data(current_page=page)
    total_pages = math.ceil(total / LIMIT) if total > 0 else 1

    if query:
        header = get_localized_message("admin_search_results_title", lang).format(
            query_text=query, current_page=page, total_pages=total_pages, total_orders=total
        )
    else:
        header = get_localized_message("admin_orders_list_title", lang).format(
            current_page=page, total_pages=total_pages, total_orders=total
        )

    text = header + "\n\n"
    if not orders:
        text += get_localized_message("no_orders_on_page", lang)

    final = InlineKeyboardBuilder()
    order_builder = InlineKeyboardBuilder()
    for order in orders:
        preview = order.order_text[:MAX_PREV] + ("..." if len(order.order_text) > MAX_PREV else "")
        nav = f"all:{page}" if not is_search else f"search:{page}:{urllib.parse.quote_plus(query or '')}"
        order_builder.add(InlineKeyboardButton(
            text=f"ID: {order.id} | {preview}",
            callback_data=f"view_order_details:{order.id}:{nav}"
        ))
    order_builder.adjust(1)
    final.attach(order_builder)

    page_prefix = "admin_search_page" if is_search else "admin_all_orders_page"
    enc_q = urllib.parse.quote_plus(query) if query else ""
    q_suf = f":{enc_q}" if enc_q else ""
    if total > LIMIT:
        pag = InlineKeyboardBuilder()
        if page > 1:
            pag.button(text="⏮️", callback_data=f"{page_prefix}:1{q_suf}")
            if page > 5:
                pag.button(text=get_localized_message("pagination_prev_5", lang), callback_data=f"{page_prefix}:{max(1,page-5)}{q_suf}")
            pag.button(text=get_localized_message("pagination_prev", lang), callback_data=f"{page_prefix}:{page-1}{q_suf}")
        if page < total_pages:
            pag.button(text=get_localized_message("pagination_next", lang), callback_data=f"{page_prefix}:{page+1}{q_suf}")
            if page < total_pages - 4:
                pag.button(text=get_localized_message("pagination_next_5", lang), callback_data=f"{page_prefix}:{min(total_pages,page+5)}{q_suf}")
            pag.button(text="⏭️", callback_data=f"{page_prefix}:{total_pages}{q_suf}")
        final.row(*pag.buttons)

    exp_cb = "export_all_orders_csv" if not is_search else f"export_search_orders_csv:{enc_q}"
    final.row(InlineKeyboardButton(text=get_localized_message("button_export_csv", lang), callback_data=exp_cb))
    final.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang), callback_data="admin_panel_back"))

    if isinstance(update, Message):
        await update.answer(text, reply_markup=final.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await update.answer()
        await update.message.edit_text(text, reply_markup=final.as_markup(), parse_mode=ParseMode.HTML)


async def _show_order_detail(
    update: Union[Message, CallbackQuery],
    state: FSMContext,
    order_id: int,
    lang: str,
) -> None:
    """Display order details with management buttons."""
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        order = await order_repo.get_by_id(order_id)

    if not order:
        err = get_localized_message("order_not_found", lang).format(order_id=order_id)
        await _alert(update, err)
        await _show_order_list(update, state, lang, page=1)
        return

    await state.update_data(current_order_id=order_id)

    text = get_localized_message("order_details_title", lang).format(order_id=order.id) + "\n\n"
    uname = f"@{html.escape(order.username)}" if order.username else get_localized_message("not_available", lang)
    text += get_localized_message("order_details_user", lang).format(username=uname, user_id=order.user_id) + "\n"
    text += get_localized_message("order_details_status", lang).format(status=get_localized_message(f"order_status_{order.status}", lang)) + "\n"

    for field_key, loc_key in ORDER_FIELD_NAMES_KEYS.items():
        field_name = get_localized_message(loc_key, lang)
        value = getattr(order, field_key)
        if field_key == "payment_method" and value:
            opts = ORDER_FIELD_MAP.get("payment_method", {}).get("options_keys", {})
            lk = next((k for k, v in opts.items() if v == value), None)
            if lk:
                value = get_localized_message(lk, lang)
        elif field_key == "delivery_notes" and (value is None or str(value).strip() in ["-", get_localized_message("no_notes_keyword", lang).lower()]):
            value = get_localized_message("no_notes_display", lang)
        elif value is None:
            value = get_localized_message("not_specified", lang)
        escaped = html.escape(str(value))
        if field_key == "order_text":
            text += get_localized_message("order_details_order_text", lang).format(order_text=escaped) + "\n"
        else:
            text += f"<b>{field_name}</b>: {escaped}\n"

    text += get_localized_message("order_details_created_at", lang).format(created_at=order.created_at.strftime("%d.%m.%Y %H:%M")) + "\n"

    kb = InlineKeyboardBuilder()
    for status_key in ORDER_STATUS_KEYS:
        if status_key != order.status:
            sname = get_localized_message(f"order_status_{status_key}", lang)
            kb.button(
                text=get_localized_message("admin_change_status_button", lang).format(status_name=sname),
                callback_data=f"admin_change_order_status:{order.id}:{status_key}"
            )
    kb.adjust(2)
    kb.row(InlineKeyboardButton(text=get_localized_message("admin_edit_text_button", lang), callback_data=f"admin_edit_order_text:{order.id}"))
    kb.row(InlineKeyboardButton(text=get_localized_message("admin_delete_order_button", lang), callback_data=f"admin_confirm_delete_order:{order.id}"))

    data = await state.get_data()
    origin_type = data.get("origin_type", "all")
    origin_page = data.get("origin_page", 1)
    origin_query = data.get("origin_search_query")
    if origin_type == "all":
        back_cb = f"admin_all_orders_page:{origin_page}"
    elif origin_type == "search" and origin_query:
        back_cb = f"admin_search_page:{origin_page}:{urllib.parse.quote_plus(origin_query)}"
    else:
        back_cb = "admin_panel_back"

    kb.row(InlineKeyboardButton(text=get_localized_message("button_back_to_orders", lang), callback_data=back_cb))

    if isinstance(update, Message):
        await update.answer(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)
    else:
        await update.answer()
        await update.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML)


async def _alert(update: Union[Message, CallbackQuery], text: str) -> None:
    if isinstance(update, CallbackQuery):
        await update.answer(text, show_alert=True)


# ─── all orders handlers ─────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_all_orders_start", IsAdmin())
async def all_orders_start(callback: CallbackQuery, state: FSMContext, lang: str):
    await state.update_data(search_query=None)
    await _show_order_list(callback, state, lang, page=1, is_search=False)


@router.callback_query(F.data.startswith("admin_all_orders_page:"), IsAdmin())
async def all_orders_page(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    await _show_order_list(callback, state, lang, page=page, is_search=False)


# ─── search handlers ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_find_orders", IsAdmin())
async def find_orders_start(callback: CallbackQuery, state: FSMContext, lang: str):
    await state.set_state(AdminStates.waiting_for_search_query)
    from aiogram.types import InlineKeyboardMarkup
    kb = InlineKeyboardBuilder()
    kb.button(text=get_localized_message("admin_cancel_search_button", lang), callback_data="admin_panel_back")
    await callback.message.edit_text(
        get_localized_message("admin_prompt_search_query", lang),
        reply_markup=kb.as_markup()
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_search_query, IsAdmin())
async def process_search_query(message: Message, state: FSMContext, lang: str):
    query = message.text.strip()
    if not query:
        await message.answer(get_localized_message("admin_prompt_search_query", lang))
        return
    await state.update_data(search_query=query)
    await _show_order_list(message, state, lang, page=1, is_search=True)


@router.callback_query(F.data.startswith("admin_search_page:"), IsAdmin())
async def search_page(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        parts = callback.data.split(":")
        page = int(parts[1])
        query = urllib.parse.unquote_plus(parts[2]) if len(parts) > 2 else ""
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    if query:
        await state.update_data(search_query=query)
    await _show_order_list(callback, state, lang, page=page, is_search=True)


# ─── order details ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("view_order_details:"), IsAdmin())
async def view_order_details(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        parts = callback.data.split(":")
        order_id = int(parts[1])
        origin_type = parts[2]
        origin_page = int(parts[3])
        origin_query = urllib.parse.unquote_plus(parts[4]) if len(parts) > 4 else None
        await state.update_data(origin_type=origin_type, origin_page=origin_page, origin_search_query=origin_query)
    except (ValueError, IndexError) as e:
        logger.error(f"Bad view_order_details callback: {callback.data} - {e}")
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    await _show_order_detail(callback, state, order_id, lang)


# ─── status change ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_change_order_status:"), IsAdmin())
async def change_order_status(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        parts = callback.data.split(":")
        order_id = int(parts[1])
        new_status = parts[2]
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        order = await order_repo.get_by_id(order_id)

        if not order:
            await callback.answer(get_localized_message("admin_status_change_failed_alert", lang).format(order_id=order_id), show_alert=True)
            return

        success = await order_repo.update_status(order_id, new_status)

        if success:
            status_name = get_localized_message(f"order_status_{new_status}", lang)
            await callback.answer(
                get_localized_message("admin_status_changed_alert", lang).format(order_id=order_id, status_name=status_name),
                show_alert=True,
            )
        else:
            await callback.answer(get_localized_message("admin_status_change_failed_alert", lang).format(order_id=order_id), show_alert=True)

    await _show_order_detail(callback, state, order_id, lang)


# ─── edit order text ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_edit_order_text:"), IsAdmin())
async def begin_edit_order_text(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    await state.update_data(editing_order_id=order_id)
    await state.set_state(AdminStates.waiting_for_new_order_text)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=get_localized_message("admin_edit_order_text_cancel_button", lang), callback_data=f"admin_cancel_edit_order_text:{order_id}"))
    await callback.message.edit_text(
        get_localized_message("admin_edit_order_text_prompt", lang).format(order_id=order_id),
        reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.message(AdminStates.waiting_for_new_order_text, IsAdmin())
async def save_new_order_text(message: Message, state: FSMContext, lang: str):
    new_text = message.text.strip()
    data = await state.get_data()
    order_id = data.get("editing_order_id")
    if not order_id:
        await message.answer(get_localized_message("admin_edit_text_error_data_not_found", lang))
        await state.clear()
        return

    async with get_db_session() as session:
        success = await OrderRepository(session).update_text(order_id, new_text)

    if success:
        await message.answer(get_localized_message("admin_order_text_updated_success", lang).format(order_id=order_id), parse_mode=ParseMode.HTML)
    else:
        await message.answer(get_localized_message("admin_order_text_update_failed", lang).format(order_id=order_id), parse_mode=ParseMode.HTML)
    await state.clear()
    await _show_order_detail(message, state, order_id, lang)


@router.callback_query(F.data.startswith("admin_cancel_edit_order_text:"), IsAdmin())
async def cancel_edit_order_text(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    await state.clear()
    await callback.answer(get_localized_message("admin_edit_text_cancelled_alert", lang), show_alert=True)
    await _show_order_detail(callback, state, order_id, lang)


# ─── delete order ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_confirm_delete_order:"), IsAdmin())
async def confirm_delete_order(callback: CallbackQuery, lang: str):
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text=get_localized_message("button_yes_delete", lang), callback_data=f"admin_delete_order:{order_id}"))
    kb.row(InlineKeyboardButton(text=get_localized_message("button_no_cancel", lang), callback_data=f"view_order_details:{order_id}:all:1"))
    await callback.message.edit_text(
        get_localized_message("admin_confirm_delete_prompt", lang).format(order_id=order_id),
        reply_markup=kb.as_markup(), parse_mode=ParseMode.HTML
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_delete_order:"), IsAdmin())
async def delete_order_confirmed(callback: CallbackQuery, state: FSMContext, lang: str):
    try:
        order_id = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer(get_localized_message("error_invalid_callback_data", lang), show_alert=True)
        return

    async with get_db_session() as session:
        success = await OrderRepository(session).delete(order_id)

    if success:
        await callback.answer(get_localized_message("admin_order_deleted_success_alert", lang).format(order_id=order_id), show_alert=True)
        await callback.message.edit_text(get_localized_message("admin_order_deleted_success_message", lang).format(order_id=order_id), parse_mode=ParseMode.HTML)
    else:
        await callback.answer(get_localized_message("admin_order_delete_failed_alert", lang).format(order_id=order_id), show_alert=True)

    await state.clear()
    await _show_order_list(callback, state, lang, page=1)


# ─── CSV export ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "export_all_orders_csv", IsAdmin())
async def export_all_csv(callback: CallbackQuery, bot: Bot, lang: str):
    await callback.answer(get_localized_message("thank_you_processing", lang))
    try:
        async with get_db_session() as session:
            orders, _ = await OrderRepository(session).get_all(offset=0, limit=10000)
        if not orders:
            await callback.message.answer(get_localized_message("export_csv_no_data_alert", lang))
            return
        from bot.handlers.admin.admin_export import generate_orders_csv
        csv_bytes = await generate_orders_csv(orders, lang)
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=BufferedInputFile(csv_bytes.getvalue(), filename="all_orders.csv"),
            caption=get_localized_message("export_csv_success_alert", lang),
        )
    except Exception as e:
        logger.error(f"CSV export error: {e}", exc_info=True)
        await callback.message.answer(get_localized_message("export_csv_error_alert", lang))


@router.callback_query(F.data.startswith("export_search_orders_csv:"), IsAdmin())
async def export_search_csv(callback: CallbackQuery, bot: Bot, lang: str):
    await callback.answer(get_localized_message("thank_you_processing", lang))
    try:
        enc_q = callback.data.split(":")[1] if ":" in callback.data else ""
        query = urllib.parse.unquote_plus(enc_q)
        async with get_db_session() as session:
            orders, _ = await OrderRepository(session).search(query, offset=0, limit=10000)
        if not orders:
            await callback.message.answer(get_localized_message("export_csv_no_data_alert", lang))
            return
        from bot.handlers.admin.admin_export import generate_orders_csv
        csv_bytes = await generate_orders_csv(orders, lang)
        fname = f"search_{query.replace(' ', '_')}.csv"
        await bot.send_document(
            chat_id=callback.from_user.id,
            document=BufferedInputFile(csv_bytes.getvalue(), filename=fname),
            caption=get_localized_message("export_csv_success_alert", lang),
        )
    except Exception as e:
        logger.error(f"CSV search export error: {e}", exc_info=True)
        await callback.message.answer(get_localized_message("export_csv_error_alert", lang))

