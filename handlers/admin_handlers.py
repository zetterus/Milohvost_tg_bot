# handlers/admin_handlers.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import logging

from config import ADMIN_IDS  # Импортируем список ID администраторов
from db import get_all_orders
from models import Order, HelpMessage # Импортируем модели

logger = logging.getLogger(__name__)

# Создаем роутер для обработки команд и коллбэков админов
admin_router = Router()


class AdminHandlers:
    """
    Класс для обработки команд и взаимодействий администраторов.
    """

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
        """
        if callback.from_user.id not in ADMIN_IDS:
            await callback.answer("У вас нет прав.")
            return

        logger.info(f"Админ {callback.from_user.id} просматривает все заказы.")

        orders_text = "Все заказы:\n\n"
        # Используем новую функцию из db.py для получения всех заказов
        orders = await get_all_orders(limit=10)  # <-- ИЗМЕНЕНО

        if orders:
            for order in orders:
                orders_text += (
                    f"ID: {order.id}\n"
                    f"От: {order.username or 'N/A'} ({order.user_id})\n"
                    f"Текст: {order.order_text[:50]}...\n"
                    f"Статус: {order.status}\n"
                    f"Создан: {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
                    "--------------------------\n"
                )
        else:
            orders_text = "Заказов пока нет."

        await callback.message.edit_text(orders_text)
        await callback.answer()

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