# db.py
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine  # Используем асинхронные версии
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select, func
from contextlib import asynccontextmanager
from typing import List, Optional

from config import DATABASE_NAME, LOGGING_LEVEL, ORDERS_PER_PAGE, ACTIVE_ORDER_STATUSES
from models import Base, Order  # Импортируем Base, чтобы создать таблицы через него

# Настройка логирования
logging.basicConfig(level=LOGGING_LEVEL)
logger = logging.getLogger(__name__)

# Асинхронный движок базы данных
engine: AsyncEngine = create_async_engine(
    f"sqlite+aiosqlite:///{DATABASE_NAME}",
    echo=False # Устанавливаем в True для логирования всех SQL-запросов (полезно для отладки)
)

# Асинхронная фабрика сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,  # <-- Указываем, что это асинхронная сессия
    expire_on_commit=False, # Обычно полезно, чтобы объекты не "отвязывались" после коммита
    autocommit=False, # <-- Убедись, что эти параметры стоят в правильном порядке или переданы как ключевые аргументы
    autoflush=False
)


@asynccontextmanager  # <-- ДОБАВЛЕНО
async def get_db_session():  # <-- ИЗМЕНЕНО ИМЯ ФУНКЦИИ
    """
    Асинхронный генератор для получения сессии базы данных.
    Используется как асинхронный контекстный менеджер.
    """
    db: AsyncSession = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()  # <-- Асинхронное закрытие сессии


async def create_tables_async() -> None:  # <-- ДОБАВЛЕНО: новая асинхронная функция
    """
    Создает таблицы базы данных асинхронно.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(
        f"База данных '{DATABASE_NAME}' и таблицы успешно созданы/обновлены с использованием SQLAlchemy (асинхронно).")


async def add_new_order(
    user_id: int,
    username: Optional[str],
    order_text: str,
    full_name: Optional[str] = None,
    delivery_address: Optional[str] = None,
    payment_method: Optional[str] = None,
    contact_phone: Optional[str] = None,
    delivery_notes: Optional[str] = None
) -> Order:
    """
    Добавляет новый заказ в базу данных.
    Принимает отдельные параметры с данными заказа и возвращает объект Order.
    """
    async with get_db_session() as db:
        new_order = Order(
            user_id=user_id,
            username=username,
            order_text=order_text,
            full_name=full_name,
            delivery_address=delivery_address,
            payment_method=payment_method,
            contact_phone=contact_phone,
            delivery_notes=delivery_notes,
            status='new' # Изначальный статус должен быть 'new'
        )
        db.add(new_order)
        await db.commit()
        await db.refresh(new_order)
        logger.info(f"Заказ ID {new_order.id} успешно добавлен в БД.")
        return new_order


async def get_all_orders(limit: int = 10) -> List[Order]:
    """
    Получает последние заказы из базы данных.
    :param limit: Максимальное количество заказов для возврата.
    :return: Список объектов Order.
    """
    async with get_db_session() as db:
        result = await db.execute(
            select(Order).order_by(Order.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


async def get_active_help_message_from_db():
    """
    Получает активное сообщение помощи из базы данных.
    """
    from models import HelpMessage  # Импортируем здесь, чтобы избежать циклического импорта
    async with get_db_session() as db:
        query = select(HelpMessage).where(HelpMessage.is_active == True)
        active_message = await db.scalar(query)
        return active_message


async def get_user_orders_paginated(user_id: int, offset: int, limit: int) -> List[Order]:
    """
    Получает АКТИВНЫЕ заказы конкретного пользователя с пагинацией.
    :param user_id: ID пользователя.
    :param offset: Смещение (количество пропускаемых записей).
    :param limit: Максимальное количество записей для возврата (количество на странице).
    :return: Список объектов Order.
    """
    async with get_db_session() as db:
        orders = await db.execute(
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.status.in_(ACTIVE_ORDER_STATUSES)
            )
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(orders.scalars().all())


async def count_user_orders(user_id: int) -> int:
    """
    Считает общее количество АКТИВНЫХ заказов для конкретного пользователя.
    """
    async with get_db_session() as db:
        total_orders = await db.scalar(
            select(func.count(Order.id))
            .where(
                Order.user_id == user_id,
                Order.status.in_(ACTIVE_ORDER_STATUSES) # <-- НОВОЕ УСЛОВИЕ ФИЛЬТРАЦИИ
            )
        )
        return total_orders if total_orders is not None else 0

async def get_order_by_id(order_id: int) -> Optional[Order]:
    """
    Получает заказ по его ID.
    :param order_id: ID заказа.
    :return: Объект Order или None, если заказ не найден.
    """
    async with get_db_session() as db:
        order = await db.get(Order, order_id) # Используем db.get для получения по первичному ключу
        return order

async def update_order_status(order_id: int, new_status: str) -> Optional[Order]:
    """
    Обновляет статус заказа в базе данных.
    :param order_id: ID заказа.
    :param new_status: Новый статус для заказа.
    :return: Обновленный объект Order или None, если заказ не найден.
    """
    async with get_db_session() as db:
        order = await db.get(Order, order_id)
        if order:
            order.status = new_status
            await db.commit()
            await db.refresh(order)
            logger.info(f"Статус заказа ID {order.id} обновлен на '{new_status}'.")
            return order
        logger.warning(f"Попытка обновить статус несуществующего заказа ID {order_id}.")
        return None
