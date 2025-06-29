# db.py
import logging
import datetime
import sqlite3
from typing import List, Optional
from contextlib import asynccontextmanager
from sqlalchemy import text, select, func, or_, Column, Integer, String, Text, DateTime, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine  # Используем асинхронные версии
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection

from config import DATABASE_NAME, LOGGING_LEVEL, ORDERS_PER_PAGE, ACTIVE_ORDER_STATUSES
from models import Base, Order  # Импортируем Base, чтобы создать таблицы через него

# Настройка логирования
logging.basicConfig(level=LOGGING_LEVEL)
logger = logging.getLogger(__name__)


# Пользовательская функция LOWER для SQLite с поддержкой Unicode ---
def _sqlite_unicode_lower(value: str) -> str | None:
    """
    Пользовательская функция для SQLite, которая корректно переводит
    строки Unicode (включая кириллицу) в нижний регистр.
    """
    if value is None:
        return None
    return value.lower()

# Асинхронный движок базы данных
engine: AsyncEngine = create_async_engine(
    f"sqlite+aiosqlite:///{DATABASE_NAME}",
    echo=False, # Установите в True, чтобы видеть сгенерированные SQL-запросы в консоли
    pool_pre_ping=True
)

@event.listens_for(engine.sync_engine, "connect")
def _register_sqlite_functions_and_pragmas(dbapi_connection, connection_record):
    """
    Слушатель, который получает объект адаптера DBAPI (AsyncAdapt_aiosqlite_connection),
    использует его напрямую для регистрации пользовательских функций и установки прагм.
    """
    # Проверяем, что dbapi_connection является ожидаемым адаптером
    if isinstance(dbapi_connection, AsyncAdapt_aiosqlite_connection):
        # 1. Регистрация пользовательской функции LOWER
        # Ожидаем, что AsyncAdapt_aiosqlite_connection имеет метод create_function
        dbapi_connection.create_function("LOWER", 1, _sqlite_unicode_lower)
        logger.debug("SQLite: Пользовательская функция LOWER (Unicode-aware) успешно зарегистрирована.")

        # 2. Установка прагм
        try:
            # Ожидаем, что AsyncAdapt_aiosqlite_connection имеет метод execute
            # Это синхронный execute, который делегирует асинхронному.
            dbapi_connection.execute("PRAGMA journal_mode = WAL;")
            dbapi_connection.execute("PRAGMA foreign_keys = ON;")
            logger.debug("SQLite: Прагмы 'journal_mode=WAL' и 'foreign_keys=ON' успешно установлены.")
        except Exception as e:
            logger.error(f"Ошибка при установке прагм SQLite: {e}")
    else:
        # Если тип соединения неожиданный, логируем ошибку
        logger.error(f"Слушатель событий получил неожиданный тип DBAPI-соединения: {type(dbapi_connection)}. Ожидается AsyncAdapt_aiosqlite_connection.")

# Асинхронная фабрика сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


@asynccontextmanager
async def get_db_session():
    """
    Асинхронный генератор для получения сессии базы данных.
    Используется как асинхронный контекстный менеджер.
    """
    db: AsyncSession = AsyncSessionLocal()
    try:
        yield db
    finally:
        await db.close()  # <-- Асинхронное закрытие сессии


async def create_tables_async() -> None:
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
            status='new'  # Изначальный статус должен быть 'new'
        )
        db.add(new_order)
        await db.commit()
        await db.refresh(new_order)
        logger.info(f"Заказ ID {new_order.id} успешно добавлен в БД.")
        return new_order


async def get_all_orders(limit: Optional[int] = None) -> List[Order]:
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
                Order.status.in_(ACTIVE_ORDER_STATUSES)  # <-- НОВОЕ УСЛОВИЕ ФИЛЬТРАЦИИ
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
        order = await db.get(Order, order_id)  # Используем db.get для получения по первичному ключу
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


async def search_orders(search_query: str) -> List[Order]:
    """
    Ищет заказы по user_id, ID заказа, части имени пользователя или части текста заказа.
    Теперь полагается на корректную работу func.lower() благодаря пользовательской функции SQLite.
    """
    async with get_db_session() as db:
        search_query_orig = search_query.strip()  # Сохраняем оригинальный запрос для логирования
        search_query_lower = search_query_orig.lower()  # Преобразуем запрос к нижнему регистру

        is_numeric_query = False
        try:
            numeric_query_value = int(search_query_orig)
            is_numeric_query = True
        except ValueError:
            numeric_query_value = None

        conditions = []  # Список условий для WHERE-clause

        if is_numeric_query and numeric_query_value is not None:
            # Если запрос - число, ищем по user_id ИЛИ Order.id
            conditions.append(or_(
                Order.user_id == numeric_query_value,
                Order.id == numeric_query_value
            ))

        # Теперь func.lower() будет работать корректно для ВСЕХ символов (включая кириллицу)
        # так как мы заменили стандартную функцию SQLite на свою.
        conditions.append(func.lower(Order.username).like(f"%{search_query_lower}%"))
        conditions.append(func.lower(Order.order_text).like(f"%{search_query_lower}%"))

        if not conditions:
            logger.warning(f"Пустой список условий для поиска запроса: '{search_query_orig}'")
            return []

        # Объединяем все условия через OR
        stmt = select(Order).where(or_(*conditions)).order_by(Order.created_at.desc())

        try:
            # Логируем сгенерированный SQL-запрос для отладки
            logger.debug(
                f"Выполняется SQL-запрос для поиска: {stmt.compile(engine, compile_kwargs={'literal_binds': True})}")

            result = await db.execute(stmt)
            orders = list(result.scalars().all())
            logger.info(f"Найдено {len(orders)} заказов по запросу: '{search_query_orig}'.")
            return orders
        except Exception as e:
            logger.error(f"Ошибка при поиске заказов в БД: {e}")
            return []


async def get_active_help_message_from_db():
    """
    Получает активное сообщение помощи из базы данных.
    """
    from models import HelpMessage  # Импортируем здесь, чтобы избежать циклического импорта
    async with get_db_session() as db:
        query = select(HelpMessage).where(HelpMessage.is_active == True)
        active_message = await db.scalar(query)
        return active_message
