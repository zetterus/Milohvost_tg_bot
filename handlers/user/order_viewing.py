import logging
from typing import Union
import html

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage, StorageKey

from db import get_user_orders_paginated, count_user_orders
from config import ORDERS_PER_PAGE, MAX_PREVIEW_TEXT_LENGTH  # ORDER_STATUS_KEYS удален
from localization import get_localized_message

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "view_my_orders")
async def view_my_orders_callback(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обрабатывает нажатие инлайн-кнопки "Посмотреть мои заказы".
    Переводит пользователя на первую страницу его заказов.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} нажал 'Посмотреть мои заказы'.")
    await _show_user_orders(callback, state, bot, storage=storage, storage_key=storage_key, page=0)


async def _show_user_orders(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        bot: Bot,
        storage: BaseStorage,
        storage_key: StorageKey,
        page: int = 0
):
    """
    Показывает пользователю его заказы с пагинацией.
    Редактирует или отправляет сообщение в зависимости от типа update_object,
    используя предоставленный объект `bot` и локализацию.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение.
    :param state: FSMContext для управления состоянием.
    :param bot: Экземпляр объекта Bot (обязательно для отправки/редактирования сообщений).
    :param storage: Объект Storage для доступа к персистентным данным пользователя.
    :param storage_key: StorageKey для идентификации данных пользователя.
    :param page: Текущий номер отображаемой страницы (начинается с 0).
    """
    user_id = update_object.from_user.id
    chat_id = update_object.message.chat.id if isinstance(update_object, CallbackQuery) else update_object.chat.id
    message_id = update_object.message.message_id if isinstance(update_object,
                                                                CallbackQuery) else update_object.message_id

    # Получаем язык пользователя из Storage
    user_storage_data = await storage.get_data(key=storage_key)
    lang = user_storage_data.get('lang', 'uk')

    offset = page * ORDERS_PER_PAGE

    user_orders = await get_user_orders_paginated(user_id, offset, ORDERS_PER_PAGE)
    total_orders = await count_user_orders(user_id)
    total_pages = (total_orders + ORDERS_PER_PAGE - 1) // ORDERS_PER_PAGE if total_orders > 0 else 1

    orders_list_text = get_localized_message("my_orders_list_title", lang).format(
        current_page=page + 1, total_pages=total_pages
    ) + "\n\n"
    keyboard = InlineKeyboardBuilder()

    if user_orders:
        for i, order in enumerate(user_orders):
            display_status = get_localized_message(f"order_status_{order.status}", lang)

            preview_text = order.order_text[:MAX_PREVIEW_TEXT_LENGTH]
            if len(order.order_text) > MAX_PREVIEW_TEXT_LENGTH:
                preview_text += "..."

            escaped_preview_text = html.escape(preview_text)

            orders_list_text += (
                f"<b>{get_localized_message('order_details_order_id', lang).format(order_id=order.id)}</b> "
                f"({get_localized_message('order_details_status_prefix', lang)}: {display_status})\n"
                f"  <i>{get_localized_message('order_details_text', lang).format(preview_text=escaped_preview_text)}</i>\n"
                f"  <i>{get_localized_message('order_details_date', lang).format(date=order.created_at.strftime('%d.%m.%Y %H:%M'))}</i>\n"
            )
            if i < len(user_orders) - 1:
                orders_list_text += get_localized_message("order_divider", lang) + "\n"

        if page > 0:
            keyboard.button(text=get_localized_message("pagination_prev", lang),
                            callback_data=f"my_orders_page:{page - 1}")
        if page < total_pages - 1:
            keyboard.button(text=get_localized_message("pagination_next", lang),
                            callback_data=f"my_orders_page:{page + 1}")
        keyboard.adjust(2)

    else:
        orders_list_text = get_localized_message("no_orders_yet", lang)

    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang),
                                      callback_data="user_main_menu_back"))

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await bot.send_message(
            chat_id=chat_id,
            text=orders_list_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
    elif isinstance(update_object, CallbackQuery):
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=orders_list_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        await update_object.answer()

    await state.update_data(current_orders_page=page)


@router.callback_query(F.data.startswith("my_orders_page:"))
async def navigate_my_orders_page(
        callback: CallbackQuery,
        state: FSMContext,
        bot: Bot,
        storage: BaseStorage,
        storage_key: StorageKey
):
    """
    Обрабатывает нажатия кнопок пагинации для заказов пользователя.
    """
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} перешел на страницу {page} заказов.")
    await _show_user_orders(callback, state, bot, storage=storage, storage_key=storage_key, page=page)
