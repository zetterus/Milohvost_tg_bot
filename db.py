# db.py
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession  # Используем асинхронные версии
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, select, func
from contextlib import asynccontextmanager

from config import DATABASE_NAME, LOGGING_LEVEL, ORDERS_PER_PAGE, ACTIVE_ORDER_STATUSES
from models import Base, Order  # Импортируем Base, чтобы создать таблицы через него

# Настройка логирования
logging.basicConfig(level=LOGGING_LEVEL)
logger = logging.getLogger(__name__)

# Асинхронный движок базы данных
engine = create_async_engine(f'sqlite+aiosqlite:///{DATABASE_NAME}')

# Асинхронная фабрика сессий
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,  # <-- Указываем, что это асинхронная сессия
    expire_on_commit=False  # Обычно полезно, чтобы объекты не "отвязывались" после коммита
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


async def add_new_order(order_data: dict) -> Order:
    """
    Добавляет новый заказ в базу данных.
    Принимает словарь с данными заказа и возвращает объект Order.
    """
    async with get_db_session() as db:
        new_order = Order(
            user_id=order_data['user_id'],
            username=order_data['username'],
            order_text=order_data['order_text'],
            full_name=order_data.get('full_name'),
            delivery_address=order_data.get('delivery_address'),
            payment_method=order_data.get('payment_method'),
            contact_phone=order_data.get('contact_phone'),
            delivery_notes=order_data.get('delivery_notes'),
            status='pending'
        )
        db.add(new_order)
        await db.commit()
        await db.refresh(new_order)  # Обновляем объект, чтобы получить ID
        logger.info(f"Заказ ID {new_order.id} успешно добавлен в БД.")
        return new_order


async def get_all_orders(limit: int = 10) -> list[Order]:
    """
    Получает список последних заказов из базы данных.
    """
    async with get_db_session() as db:
        orders = await db.execute(select(Order).order_by(Order.created_at.desc()).limit(limit))
        return orders.scalars().all()


async def get_active_help_message_from_db():
    """
    Получает активное сообщение помощи из базы данных.
    """
    from models import HelpMessage  # Импортируем здесь, чтобы избежать циклического импорта
    async with get_db_session() as db:
        query = select(HelpMessage).where(HelpMessage.is_active == True)
        active_message = await db.scalar(query)
        return active_message


async def get_user_orders_paginated(user_id: int, offset: int, limit: int) -> list[Order]:
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
                Order.status.in_(ACTIVE_ORDER_STATUSES) # <-- НОВОЕ УСЛОВИЕ ФИЛЬТРАЦИИ
            )
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return orders.scalars().all()

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
