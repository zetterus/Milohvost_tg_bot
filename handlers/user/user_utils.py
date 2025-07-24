import logging
from typing import Union

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode

from localization import get_localized_message
from db import update_user_language, get_user_language_code, get_user_notifications_status, \
    update_user_notifications_status, get_or_create_user, get_order_by_id  # Добавлен импорт get_order_by_id
from config import ADMIN_IDS
from models import Order, User  # Добавлен импорт User для типизации

logger = logging.getLogger(__name__)
router = Router()


# --- Вспомогательная функция для отображения главного меню пользователя ---
async def _display_user_main_menu(
        update_object: Union[Message, CallbackQuery],
        state: FSMContext,
        lang: str
):
    """
    Отображает главное меню для пользователя, сбрасывая его FSM-состояние.
    Сообщение отправляется или редактируется в зависимости от типа объекта обновления.
    Использует локализованные тексты.

    :param update_object: Объект Message или CallbackQuery, инициировавший отображение меню.
    :param state: FSMContext для управления состоянием пользователя.
    :param lang: Код языка для локализации текстов.
    """
    user_id = update_object.from_user.id
    logger.info(f"Пользователь {user_id} переходит в главное меню (язык: {lang}).")

    await state.clear()

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text=get_localized_message("button_make_order", lang), callback_data="make_order")
    keyboard.button(text=get_localized_message("button_view_my_orders", lang), callback_data="view_my_orders")
    keyboard.button(text=get_localized_message("button_get_help", lang), callback_data="get_help")
    keyboard.button(text=get_localized_message("button_my_language", lang), callback_data="show_language_options")
    keyboard.button(text=get_localized_message("button_notification_settings", lang),
                    callback_data="show_notification_settings")  # НОВАЯ КНОПКА
    keyboard.adjust(1)

    menu_text = get_localized_message("welcome", lang)

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.answer()
        await update_object.message.edit_text(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)


# --- Вспомогательная функция для уведомления админов о новом заказе ---
async def send_new_order_notification_to_admins(bot: Bot, order_id: int):
    """
    Отправляет уведомление о новом заказе всем администраторам.
    Получает детали заказа из БД по order_id.
    Уведомления будут отправляться на языке администратора, если он указан в БД,
    иначе на языке по умолчанию (uk).
    """
    logger.info(f"Начало отправки уведомления о новом заказе ID {order_id} администраторам.")

    order = await get_order_by_id(order_id)
    if not order:
        logger.error(
            f"Ошибка: Не удалось найти заказ ID {order_id} для отправки уведомления администраторам. Уведомление не отправлено.")
        return
    else:
        logger.info(f"Получен заказ по ID. {order.id}, {order.username}")
    logger.debug(f"Заказ ID {order_id} успешно получен из БД.")

    for admin_id in ADMIN_IDS:
        logger.debug(f"Попытка отправить уведомление админу {admin_id} для заказа ID {order_id}.")
        try:
            admin_lang = await get_user_language_code(admin_id)
            logger.debug(f"Для админа {admin_id} определен язык: '{admin_lang}'.")

            # ИЗМЕНЕНО: Удален вызов get_or_create_user для order_user
            # Теперь username берется напрямую из объекта order

            title = get_localized_message("admin_new_order_notification_title", admin_lang).format(order_id=order.id)
            logger.debug(f"Заголовок уведомления для админа {admin_id}: '{title}'.")

            # ИЗМЕНЕНО: Формирование имени пользователя для отображения только из order.username
            if order.username:
                username_text = f"@{order.username}"
            else:
                username_text = get_localized_message("not_available", admin_lang)

            logger.debug(f"Username для уведомления: '{username_text}'.")

            full_name_text = order.full_name if order.full_name else get_localized_message("not_provided", admin_lang)
            logger.debug(f"Полное имя для уведомления: '{full_name_text}'.")

            phone_number_text = order.contact_phone if order.contact_phone else get_localized_message("not_provided",
                                                                                                      admin_lang)
            logger.debug(f"Телефон для уведомления: '{phone_number_text}'.")

            status_localized = get_localized_message(f"order_status_{order.status}", admin_lang)
            logger.debug(f"Локализованный статус заказа: '{status_localized}'.")

            details_template = get_localized_message("admin_new_order_notification_details", admin_lang)
            logger.debug(f"Шаблон деталей уведомления: '{details_template[:100]}...'")  # Логируем часть шаблона

            notification_text = title + "\n\n" + details_template.format(
                order_id=order.id,
                user_id=order.user_id,
                username=username_text,
                full_name=full_name_text,
                phone_number=phone_number_text,
                order_text=order.order_text,
                status=status_localized,
                created_at=order.created_at.strftime('%d.%m.%Y %H:%M')
            )
            logger.debug(
                f"Полный текст уведомления для админа {admin_id}: '{notification_text[:500]}...'")  # Логируем часть сообщения

            await bot.send_message(admin_id, notification_text, parse_mode='HTML')
            logger.info(f"Уведомление о заказе ID {order.id} успешно отправлено админу {admin_id}.")
        except Exception as e:
            logger.error(f"Критическая ошибка при отправке уведомления о заказе ID {order.id} админу {admin_id}: {e}",
                         exc_info=True)


# Отправка уведомлений пользователю
async def send_user_notification(bot: Bot, user_id: int, message_key: str, lang: str, order_id: int,
                                 **kwargs):  # ИЗМЕНЕНО: добавлено order_id
    """
    Отправляет уведомление конкретному пользователю, если у него включены уведомления.
    """
    notifications_enabled = await get_user_notifications_status(user_id)
    if notifications_enabled:
        try:
            # Получаем объект заказа, чтобы получить актуальные данные
            order = await get_order_by_id(order_id)
            if not order:
                logger.error(f"Не удалось найти заказ ID {order_id} для отправки уведомления пользователю {user_id}.")
                return

            # Теперь используем order.id для форматирования сообщения
            text = get_localized_message(message_key, lang).format(order_id=order.id, **kwargs)
            await bot.send_message(user_id, text, parse_mode=ParseMode.HTML)
            logger.info(f"Уведомление '{message_key}' отправлено пользователю {user_id}.")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление '{message_key}' пользователю {user_id}: {e}")
    else:
        logger.info(f"Уведомления для пользователя {user_id} отключены. Сообщение '{message_key}' не отправлено.")


# --- ХЕНДЛЕР для отображения опций языка ---
@router.callback_query(F.data == "show_language_options")
async def show_language_options_callback(
        callback: CallbackQuery,
        lang: str
):
    """
    Показывает пользователю опции для смены языка.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил опции языка (текущий: {lang}).")

    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🇺🇦 Українська", callback_data="set_lang_uk")
    keyboard.button(text="🇬🇧 English", callback_data="set_lang_en")
    keyboard.button(text="🇷🇺 Русский", callback_data="set_lang_ru")
    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang),
                                      callback_data="user_main_menu_back"))
    keyboard.adjust(1)

    await callback.message.edit_text(
        get_localized_message("choose_language_prompt", lang),
        reply_markup=keyboard.as_markup(),
        parse_mode=ParseMode.HTML
    )
    await callback.answer()


# --- Хендлер для получения информации о языке (перемещен из main_menu.py) ---
@router.message(F.text == "Мой язык")
async def get_my_language(
        message: Message,
        lang: str
):
    """
    Обрабатывает запрос пользователя на получение информации о текущем языке.
    """
    await message.answer(get_localized_message("your_current_language", lang).format(current_lang=lang))


# --- Хендлер для смены языка (перемещен из main_menu.py) ---
@router.callback_query(F.data.startswith("set_lang_"))
async def change_user_language(
        callback: CallbackQuery,
        lang: str
):
    """
    Обрабатывает выбор пользователя для смены языка.
    Обновляет язык в БД.
    """
    user_id = callback.from_user.id
    new_lang = callback.data.split('_')[2]

    updated_user = await update_user_language(user_id, new_lang)

    # Создаем клавиатуру с кнопкой "Назад в главное меню"
    keyboard = InlineKeyboardBuilder()
    keyboard.row(InlineKeyboardButton(
        text=get_localized_message("button_back_to_main_menu", new_lang),  # Используем new_lang для локализации кнопки
        callback_data="user_main_menu_back"
    ))
    reply_markup = keyboard.as_markup()

    if updated_user:
        # Форматируем сообщение, передавая new_lang для заполнения плейсхолдера
        success_message_text = get_localized_message("language_changed_success_alert",
                                                     updated_user.language_code).format(
            new_lang=updated_user.language_code.upper())

        # Редактируем существующее сообщение, чтобы показать подтверждение и кнопку
        await callback.message.edit_text(
            success_message_text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        await callback.answer()  # Отвечаем на callback, чтобы убрать "часики"
    else:
        error_message_text = get_localized_message("language_change_failed_alert", lang)
        # Редактируем существующее сообщение, чтобы показать ошибку и кнопку
        await callback.message.edit_text(
            error_message_text,
            reply_markup=reply_markup,  # Оставляем кнопку "Назад в главное меню" даже при ошибке
            parse_mode=ParseMode.HTML
        )
        await callback.answer()


# НОВАЯ ФУНКЦИЯ: Отображение меню настроек уведомлений
async def _display_notification_settings_menu(
        update_object: Union[Message, CallbackQuery],
        lang: str
):
    """
    Отображает меню настроек уведомлений для пользователя.
    """
    user_id = update_object.from_user.id
    current_status = await get_user_notifications_status(user_id)

    status_text_key = "notifications_enabled_status" if current_status else "notifications_disabled_status"
    status_emoji = "✅" if current_status else "❌"

    menu_text = get_localized_message("notification_settings_title", lang).format(
        current_status=get_localized_message(status_text_key, lang),
        status_emoji=status_emoji
    )

    keyboard = InlineKeyboardBuilder()
    if current_status:
        keyboard.button(text=get_localized_message("button_disable_notifications", lang),
                        callback_data="toggle_notifications_off")
    else:
        keyboard.button(text=get_localized_message("button_enable_notifications", lang),
                        callback_data="toggle_notifications_on")

    keyboard.row(InlineKeyboardButton(text=get_localized_message("button_back_to_main_menu", lang),
                                      callback_data="user_main_menu_back"))
    keyboard.adjust(1)

    reply_markup = keyboard.as_markup()

    if isinstance(update_object, Message):
        await update_object.answer(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif isinstance(update_object, CallbackQuery):
        await update_object.message.edit_text(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        await update_object.answer()


# НОВЫЙ ХЕНДЛЕР: Показать настройки уведомлений
@router.callback_query(F.data == "show_notification_settings")
async def show_notification_settings_callback(
        callback: CallbackQuery,
        lang: str
):
    """
    Обрабатывает нажатие кнопки "Настройки уведомлений" и отображает соответствующее меню.
    """
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} запросил настройки уведомлений.")
    await _display_notification_settings_menu(callback, lang)


# НОВЫЙ ХЕНДЛЕР: Включить/выключить уведомления
@router.callback_query(F.data.startswith("toggle_notifications_"))
async def toggle_notifications_callback(
        callback: CallbackQuery,
        lang: str
):
    """
    Обрабатывает нажатие кнопок включения/выключения уведомлений.
    """
    user_id = callback.from_user.id
    action = callback.data.split('_')[-1]  # 'on' или 'off'

    new_status = True if action == 'on' else False

    updated_user = await update_user_notifications_status(user_id, new_status)

    if updated_user:
        alert_text_key = "notifications_enabled_alert" if new_status else "notifications_disabled_alert"
        alert_text = get_localized_message(alert_text_key, lang)
        await callback.answer(alert_text, show_alert=True)
        logger.info(f"Уведомления для пользователя {user_id} {action}ключены.")
        # Обновляем меню после изменения статуса
        await _display_notification_settings_menu(callback, lang)
    else:
        await callback.answer(get_localized_message("notifications_toggle_failed_alert", lang), show_alert=True)
        logger.error(f"Не удалось изменить статус уведомлений для пользователя {user_id}.")
