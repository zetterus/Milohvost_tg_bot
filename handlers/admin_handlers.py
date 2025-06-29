# handlers/admin_handlers.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from aiogram.utils.markdown import hbold, hcode, hlink

import logging

from config import ADMIN_IDS, ORDER_STATUS_MAP  # Импортируем список ID администраторов
from db import get_all_orders, get_order_by_id, update_order_status
from models import Order, HelpMessage # Импортируем модели

logger = logging.getLogger(__name__)

# Создаем роутер для обработки команд и коллбэков админов
admin_router = Router()


class AdminHandlers:
    """
    Класс для обработки команд и взаимодействий администраторов.
    """

    @staticmethod
    def _escape_markdown_v2(text: str) -> str:
        """
        Экранирует ТОЛЬКО необходимые специальные символы MarkdownV2 в тексте,
        чтобы избежать ошибок парсинга Telegram, сохраняя при этом читаемость.
        Применяется к пользовательскому вводу, который не будет форматирован Markdown.
        """
        if text is None:
            return ""

        # Перечень символов, которые ОБЯЗАТЕЛЬНО нужно экранировать в MarkdownV2,
        # если они не используются по прямому назначению в синтаксисе.
        # Например, '_' - для курсива, '*' - для жирного, '[' и ']' - для ссылок и т.д.
        # Точка '.', плюс '+', минус '-' и т.п. обычно НЕ требуют экранирования в обычном тексте.
        # Символы, которые действительно часто вызывают проблемы: _ * [ ] ( ) ~ ` > # = | { } !
        # Я также добавил '.' и '-' обратно, если они потенциально могут быть в начале строки
        # и быть частью списков, но это более сложный случай. Для адреса и телефона
        # они не должны вызывать проблем.

        # Давай сосредоточимся на тех, что СТОПРОЦЕНТНО вызывают проблемы
        # и которые AIOGRAM_MD_V2.escape не обрабатывает автоматически для общего текста.

        # Вот список, который Aiogram рекомендует для ОБЩЕГО escape:
        # _ * [ ] ( ) ~ ` > # + - = | { } . !

        # Но для большинства ПОЛЕЙ (адрес, телефон), где нет форматирования,
        # проблемы вызывают только: _ * [ ] ( ) ~ ` > # | { } !
        # '+' и '-' - только если это начало списка.
        # '.' - только если это в конце номера списка.

        # Исправим на более точный набор для "безопасного" текста:
        # Уберем `.` и `+` и `-`, так как они чаще всего встречаются в адресах/телефонах
        # и не вызывают проблем, если не являются частью Markdown синтаксиса (например, начало списка).

        # Оставим только те, которые точно ломают разметку в середине слова:
        # _ * [ ] ( ) ~ ` > # | { } !

        # Если Telegram все еще ругается, можно будет вернуть некоторые из них.
        # Для адреса: '.', '-', '(', ')', ',' могут быть.
        # Для телефона: '+', '-', '(', ')'

        # Попробуем более минималистичный и безопасный набор, который нужен для полей,
        # таких как ФИО, адрес, телефон, где мы не ожидаем сложного Markdown,
        # но хотим избежать поломок от одиночных спецсимволов.

        special_chars_to_escape = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '=', '|', '{', '}', '!', '.']
        # Я вернул точку '.' обратно, так как она может быть проблемой в именах файлов
        # или других необычных случаях. Символ '+' и '-' пока оставим без экранирования,
        # так как они часто встречаются в телефонах и адресах, и редко ломают Markdown
        # если не используются для создания списков.

        for char in special_chars_to_escape:
            text = text.replace(char, f'\\{char}')
        return text

    @admin_router.message(Command("admin"))
    async def admin_command(message: Message):
        """
        Обрабатывает команду /admin.
        Проверяет, является ли пользователь админом, и если да,
        отправляет админское меню.
        """
        if message.from_user.id not in ADMIN_IDS:
            logger.warning(f"Попытка доступа к админ-панели от неадмина: {message.from_user.id}")
            await message.answer("У вас нет прав для доступа к этой команде.")
            return

        logger.info(f"Админ {message.from_user.id} вошел в админ-панель.")

        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Просмотреть все заказы 📋", callback_data="admin_view_all_orders")
        keyboard.button(text="Найти заказы 🔍", callback_data="admin_find_orders")
        keyboard.button(text="Управление помощью 💬", callback_data="admin_manage_help_messages")
        keyboard.adjust(1)  # Размещаем кнопки по одной в ряд

        await message.answer(
            "Добро пожаловать в админ-панель! Выберите действие:",
            reply_markup=keyboard.as_markup()
        )

    @admin_router.callback_query(F.data == "admin_view_all_orders")
    async def admin_view_all_orders_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие инлайн-кнопки "Просмотреть все заказы".
        Теперь показывает список заказов с кнопками для детального просмотра.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        logger.info(f"Админ {callback.from_user.id} просматривает все заказы.")

        orders_text = "**Последние заказы:**\n\n"
        orders = await get_all_orders(limit=10)  # Покажем последние 10 заказов для начала

        if orders:
            keyboard = InlineKeyboardBuilder()
            for order in orders:
                display_status = ORDER_STATUS_MAP.get(order.status, order.status)

                escaped_username = AdminHandlers._escape_markdown_v2(order.username or 'N/A')
                # Теперь order_text[:40] тоже должен быть экранирован,
                # если мы не используем hcode для него.
                # Поскольку мы его не оборачиваем, _escape_markdown_v2 здесь нужен!
                escaped_order_text_preview = AdminHandlers._escape_markdown_v2(order.order_text[:40])

                orders_text += (
                    f"ID: {order.id} | От: {escaped_username} | Статус: {display_status}\n"
                    f"  _Текст:_ {escaped_order_text_preview}...\n\n"
                )
                # Добавляем кнопку "Подробнее" для каждого заказа
                keyboard.add(InlineKeyboardButton(
                    text=f"👁️ Заказ №{order.id}",
                    callback_data=f"view_order_{order.id}"
                ))
            keyboard.adjust(2)  # Размещаем кнопки по 2 в ряд

            await callback.message.edit_text(
                orders_text,
                reply_markup=keyboard.as_markup(),
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text("Заказов пока нет.")

        await callback.answer()

    @classmethod
    @admin_router.callback_query(F.data.startswith("view_order_"))
    async def admin_view_order_details_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие кнопки "Заказ #ID" для детального просмотра заказа.
        Показывает подробную информацию о заказе и кнопки для изменения статуса.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        order_id = int(callback.data.split("_")[2])
        logger.info(f"Админ {callback.from_user.id} просматривает детали заказа ID {order_id}.")

        order = await get_order_by_id(order_id)

        if order:
            display_status = ORDER_STATUS_MAP.get(order.status, order.status)
            order_details_text = (
                f"**Детали заказа №{order.id}**\n\n"
                f"**Пользователь:** {AdminHandlers._escape_markdown_v2(order.username or 'N/A')} ({order.user_id})\n"
                f"**Статус:** {display_status}\n"
                f"**Текст заказа:**\n{hcode(order.order_text)}\n"  # <-- order_text БЕЗ _escape_markdown_v2()
                f"**ФИО:** {AdminHandlers._escape_markdown_v2(order.full_name or 'Не указано')}\n"
                f"**Адрес доставки:** {AdminHandlers._escape_markdown_v2(order.delivery_address or 'Не указан')}\n"
                f"**Метод оплаты:** {AdminHandlers._escape_markdown_v2(order.payment_method or 'Не указан')}\n"
                f"**Телефон:** {AdminHandlers._escape_markdown_v2(order.contact_phone or 'Не указан')}\n"
                f"**Примечания:** {AdminHandlers._escape_markdown_v2(order.delivery_notes or 'Нет')}\n"
                f"**Дата создания:** {order.created_at.strftime('%d.%m.%Y %H:%M:%S')}\n"
            )

            # Кнопки для изменения статуса
            status_keyboard = InlineKeyboardBuilder()
            for status_key, status_value in ORDER_STATUS_MAP.items():
                # Не показываем текущий статус как опцию для изменения на себя же
                if status_key != order.status:
                    status_keyboard.add(InlineKeyboardButton(
                        text=f"🔄 {status_value}",
                        callback_data=f"admin_change_status:{order.id}_{status_key}"
                    ))
            status_keyboard.add(InlineKeyboardButton(
                text="⬅️ Назад к заказам",
                callback_data="admin_view_all_orders"
            ))
            status_keyboard.adjust(2)  # Размещаем кнопки по 2 в ряд

            await callback.message.edit_text(
                order_details_text,
                reply_markup=status_keyboard.as_markup(),
                parse_mode="Markdown"
            )
        else:
            await callback.message.edit_text("Заказ не найден.")

        await callback.answer()

    @admin_router.callback_query(F.data.startswith("admin_change_status:"))
    async def admin_change_order_status_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие кнопки для изменения статуса заказа.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        parts = callback.data.split("_")
        order_id = int(parts[3])
        new_status = parts[4]

        logger.info(f"Админ {callback.from_user.id} меняет статус заказа ID {order_id} на '{new_status}'.")

        updated_order = await update_order_status(order_id, new_status)

        if updated_order:
            # После обновления статуса, возвращаемся к детальному просмотру этого же заказа
            # Или к списку всех заказов
            display_status = ORDER_STATUS_MAP.get(updated_order.status, updated_order.status)
            await callback.answer(f"Статус заказа №{order_id} изменен на '{display_status}'!", show_alert=True)
            # Вызываем тот же обработчик для обновления отображения
            await AdminHandlers.admin_view_order_details_callback(callback)  # Передаем тот же callback, чтобы обновить сообщение
        else:
            await callback.answer("Не удалось изменить статус заказа. Заказ не найден.", show_alert=True)
            await callback.message.edit_text("Ошибка: Заказ не найден.")

    @admin_router.callback_query(F.data == "admin_find_orders")
    async def admin_find_orders_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие инлайн-кнопки "Найти заказы".
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        logger.info(f"Админ {callback.from_user.id} нажал 'Найти заказы'.")
        await callback.message.edit_text("Здесь будет функционал поиска заказов. В разработке.")
        await callback.answer()

    @admin_router.callback_query(F.data == "admin_manage_help_messages")
    async def admin_manage_help_messages_callback(callback: CallbackQuery):
        """
        Обрабатывает нажатие инлайн-кнопки "Управление помощью".
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        logger.info(f"Админ {callback.from_user.id} нажал 'Управление помощью'.")
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="Создать/Редактировать сообщение ✏️", callback_data="admin_create_edit_help")
        keyboard.button(text="Выбрать активное сообщение ✅", callback_data="admin_select_active_help")
        keyboard.button(text="Назад в админ-панель 🔙", callback_data="admin_panel_back")
        keyboard.adjust(1)

        await callback.message.edit_text(
            "Управление сообщениями помощи:",
            reply_markup=keyboard.as_markup()
        )
        await callback.answer()

    # TODO: Добавить обработчики для создания/редактирования и выбора активного сообщения помощи

    @admin_router.callback_query(F.data == "admin_panel_back")
    async def admin_panel_back_callback(callback: CallbackQuery):
        """
        Возвращает админа в главное меню админ-панели.
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        await AdminHandlers.admin_command(callback.message)  # Вызываем функцию, которая отображает админ-панель
        await callback.answer()