"""Admin keyboard builders."""
import urllib.parse
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from localization import get_localized_message
from core.config import settings

ORDERS_PER_PAGE = settings.orders_per_page
MAX_PREVIEW_TEXT_LENGTH = settings.max_preview_text_length
def admin_main_menu_kb(lang: str) -> InlineKeyboardMarkup:
    """Admin main menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=get_localized_message("admin_button_all_orders", lang), callback_data="admin_all_orders_start")
    builder.button(text=get_localized_message("admin_button_find_orders", lang), callback_data="admin_find_orders")
    builder.button(text=get_localized_message("admin_button_manage_help", lang), callback_data="admin_manage_help_messages")
    builder.adjust(1)
    return builder.as_markup()
def back_to_admin_kb(lang: str) -> InlineKeyboardMarkup:
    """Back-to-admin-panel button."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang), callback_data="admin_panel_back"))
    return builder.as_markup()
def order_list_kb(orders: list, current_page: int, total_orders: int, lang: str, is_search: bool = False, query_text: str = None) -> InlineKeyboardMarkup:
    """Order list with pagination keyboard."""
    final_builder = InlineKeyboardBuilder()
    order_builder = InlineKeyboardBuilder()
    for order in orders:
        preview = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
        if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
            preview += "..."
        nav = f"all:{current_page}"
        if is_search and query_text:
            enc = urllib.parse.quote_plus(query_text)
            nav = f"search:{current_page}:{enc}"
        order_builder.add(InlineKeyboardButton(
            text=f"ID: {order.id} | {preview}",
            callback_data=f"view_order_details:{order.id}:{nav}"
        ))
    order_builder.adjust(1)
    final_builder.attach(order_builder)
    total_pages = (total_orders + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE if total_orders > 0 else 1
    page_prefix = "admin_search_page" if is_search else "admin_all_orders_page"
    enc_q = urllib.parse.quote_plus(query_text) if query_text else ""
    q_suffix = f":{enc_q}" if enc_q else ""
    if total_orders > ORDERS_PER_PAGE:
        pag = InlineKeyboardBuilder()
        if current_page > 1:
            pag.button(text="⏮️", callback_data=f"{page_prefix}:1{q_suffix}")
            if current_page > 5:
                pag.button(text=get_localized_message("pagination_prev_5", lang), callback_data=f"{page_prefix}:{max(1, current_page-5)}{q_suffix}")
            pag.button(text=get_localized_message("pagination_prev", lang), callback_data=f"{page_prefix}:{current_page-1}{q_suffix}")
        if current_page < total_pages:
            pag.button(text=get_localized_message("pagination_next", lang), callback_data=f"{page_prefix}:{current_page+1}{q_suffix}")
            if current_page < total_pages - 4:
                pag.button(text=get_localized_message("pagination_next_5", lang), callback_data=f"{page_prefix}:{min(total_pages, current_page+5)}{q_suffix}")
            pag.button(text="⏭️", callback_data=f"{page_prefix}:{total_pages}{q_suffix}")
        final_builder.row(*pag.buttons)
    export_cb = "export_all_orders_csv" if not is_search else f"export_search_orders_csv:{enc_q}"
    final_builder.row(InlineKeyboardButton(text=get_localized_message("button_export_csv", lang), callback_data=export_cb))
    final_builder.row(InlineKeyboardButton(text=get_localized_message("button_back_to_admin_panel", lang), callback_data="admin_panel_back"))
    return final_builder.as_markup()
