# db.py
import logging
from typing import List, Optional
from contextlib import asynccontextmanager
from datetime import datetime
from sqlalchemy import text, select, func, or_, Column, Integer, String, Text, DateTime, event, Boolean
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection

from config import DATABASE_NAME, LOGGING_LEVEL, ORDERS_PER_PAGE, ACTIVE_ORDER_STATUSES
from models import Base, Order, HelpMessage

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
def _register_sqlite_functions_and_pragmas(dbapi_connection, _connection_record):
    """
    Слушатель, который получает объект адаптера DBAPI (AsyncAdapt_aiosqlite_connection),
    использует его напрямую для регистрации пользовательских функций и установки прагм.
    """
    if isinstance(dbapi_connection, AsyncAdapt_aiosqlite_connection):
        dbapi_connection.create_function("LOWER", 1, _sqlite_unicode_lower)
        logger.debug("SQLite: Пользовательская функция LOWER (Unicode-aware) успешно зарегистрирована.")

        try:
            dbapi_connection.execute("PRAGMA journal_mode = WAL;")
            dbapi_connection.execute("PRAGMA foreign_keys = ON;")
            logger.debug("SQLite: Прагмы 'journal_mode=WAL' и 'foreign_keys=ON' успешно установлены.")
        except Exception as e:
            logger.error(f"Ошибка при установке прагм SQLite: {e}")
    else:
        logger.error(f"Слушатель событий получил неожиданный тип DBAPI-соединения: {type(dbapi_connection)}. Ожидается AsyncAdapt_aiosqlite_connection.")

# Асинхронная фабрика сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False # type: ignore [call-arg]
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
        await db.close()


async def create_tables_async() -> None:
    """
    Создает таблицы базы данных асинхронно.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(
        f"База данных '{DATABASE_NAME}' и таблицы успешно созданы/обновлены с использованием SQLAlchemy (асинхронно).")


# --- ФУНКЦИИ УПРАВЛЕНИЯ ЗАКАЗАМИ ---

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
            status='new'
        )
        db.add(new_order)
        await db.commit()
        await db.refresh(new_order)
        logger.info(f"Заказ ID {new_order.id} успешно добавлен в БД.")
        return new_order


async def get_all_orders(offset: int = 0, limit: Optional[int] = None) -> tuple[List[Order], int]:
    """
    Получает последние заказы из базы данных с пагинацией и общее количество.
    :param offset: Смещение для пагинации.
    :param limit: Максимальное количество заказов для возврата.
    :return: Кортеж: (список объектов Order, общее количество заказов).
    """
    async with get_db_session() as db:
        total_orders_query = select(func.count(Order.id)) # type: ignore [arg-type]
        total_orders = await db.scalar(total_orders_query) or 0

        orders_query = select(Order).order_by(Order.created_at.desc()) # type: ignore [call-overload]
        if limit is not None:
            orders_query = orders_query.offset(offset).limit(limit)

        result = await db.execute(orders_query)
        orders = list(result.scalars().all())

        return orders, total_orders


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
            select(Order) # type: ignore [call-overload]
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
            select(func.count(Order.id)) # type: ignore [arg-type]
            .where(
                Order.user_id == user_id,
                Order.status.in_(ACTIVE_ORDER_STATUSES)
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
        order = await db.get(Order, order_id)
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


async def search_orders(search_query: str, offset: int = 0, limit: Optional[int] = None) -> tuple[List[Order], int]:
    """
    Ищет заказы по user_id, ID заказа, части имени пользователя или части текста заказа.
    Поддерживает пагинацию и возвращает общее количество найденных заказов.
    :param search_query: Поисковый запрос пользователя.
    :param offset: Смещение для пагинации (количество пропускаемых записей).
    :param limit: Максимальное количество записей для возврата на одной странице.
    :return: Кортеж: (список объектов Order, общее количество найденных заказов без учета пагинации).
    """
    async with get_db_session() as db:
        search_query_orig = search_query.strip()
        search_query_lower = search_query_orig.lower()

        is_numeric_query = False
        try:
            numeric_query_value = int(search_query_orig)
            is_numeric_query = True
        except ValueError:
            numeric_query_value = None

        conditions = []

        if is_numeric_query and numeric_query_value is not None:
            conditions.append(or_(
                Order.user_id == numeric_query_value,
                Order.id == numeric_query_value
            ))

        if search_query_lower:
            conditions.append(func.lower(Order.username).like(f"%{search_query_lower}%"))
            conditions.append(func.lower(Order.order_text).like(f"%{search_query_lower}%"))

        if not conditions:
            logger.warning(f"Пустой список условий для поиска запроса: '{search_query_orig}'")
            return [], 0

        count_stmt = select(func.count(Order.id)).where(or_(*conditions)) # type: ignore [arg-type]
        total_orders = await db.scalar(count_stmt) or 0

        stmt = select(Order).where(or_(*conditions)).order_by(Order.created_at.desc()) # type: ignore [call-overload]
        if limit is not None:
            stmt = stmt.offset(offset).limit(limit)

        try:
            logger.debug(
                f"Выполняется SQL-запрос для поиска (пагинация): {stmt.compile(engine, compile_kwargs={'literal_binds': True})}")
            result = await db.execute(stmt)
            orders = list(result.scalars().all())
            logger.info(f"Найдено {len(orders)} заказов по запросу: '{search_query_orig}' (всего: {total_orders}).")
            return orders, total_orders
        except Exception as e:
            logger.error(f"Ошибка при поиске заказов в БД: {e}")
            return [], 0

async def update_order_text(order_id: int, new_text: str) -> Optional[Order]:
    """
    Обновляет текст заказа в базе данных по ID.
    Возвращает обновленный объект Order или None, если заказ не найден.
    """
    async with get_db_session() as db:
        order = await db.get(Order, order_id)
        if order:
            order.order_text = new_text
            await db.commit()
            await db.refresh(order)
            logger.info(f"Текст заказа ID {order.id} успешно обновлен.")
            return order
        logger.warning(f"Попытка обновить текст несуществующего заказа ID {order_id}.")
        return None

async def delete_order(order_id: int) -> bool:
    """
    Удаляет заказ из базы данных по ID.
    Возвращает True, если заказ был успешно удален, False в противном случае.
    """
    async with get_db_session() as db:
        order = await db.get(Order, order_id)
        if order:
            await db.delete(order)
            await db.commit()
            logger.info(f"Заказ ID {order.id} успешно удален из БД.")
            return True
        logger.warning(f"Попытка удалить несуществующий заказ ID {order_id}.")
        return False

# --- ФУНКЦИИ УПРАВЛЕНИЯ СООБЩЕНИЯМИ ПОМОЩИ ---

async def add_help_message(message_text: str, is_active: bool = False) -> HelpMessage: # <--- УДАЛЕН title
    """
    Добавляет новое сообщение помощи в базу данных.
    Если is_active=True, деактивирует все остальные сообщения.
    """
    async with get_db_session() as db:
        if is_active:
            # Деактивируем все существующие активные сообщения
            await db.execute(
                text("UPDATE help_messages SET is_active = :false WHERE is_active = :true"),
                {"false": False, "true": True}
            )
            logger.debug("Все предыдущие активные сообщения помощи деактивированы.")

        new_message = HelpMessage(
            message_text=message_text,
            is_active=is_active,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(new_message)
        await db.commit()
        await db.refresh(new_message)
        # Логирование без title
        logger.info(f"Сообщение помощи ID {new_message.id} успешно добавлено в БД (активно: {is_active}).")
        return new_message


async def get_help_message_by_id(message_id: int) -> Optional[HelpMessage]:
    """
    Получает сообщение помощи по его ID.
    """
    async with get_db_session() as db:
        message = await db.get(HelpMessage, message_id)
        return message


async def get_active_help_message_from_db() -> Optional[HelpMessage]:
    """
    Получает активное сообщение помощи из базы данных.
    """
    async with get_db_session() as db:
        query = select(HelpMessage).where(HelpMessage.is_active == True) # type: ignore [call-overload]
        active_message = await db.scalar(query)
        return active_message


async def set_active_help_message(message_id: int) -> Optional[HelpMessage]:
    """
    Устанавливает сообщение с указанным ID как активное, деактивируя все остальные.
    Возвращает активированное сообщение или None, если оно не найдено.
    """
    async with get_db_session() as db:
        # 1. Деактивировать все существующие активные сообщения
        await db.execute(
            text("UPDATE help_messages SET is_active = :false WHERE is_active = :true"),
            {"false": False, "true": True}
        )
        logger.debug("Все предыдущие активные сообщения помощи деактивированы.")

        # 2. Активировать выбранное сообщение
        selected_message = await db.get(HelpMessage, message_id)
        if selected_message:
            selected_message.is_active = True
            await db.commit()
            await db.refresh(selected_message)
            # Логирование без title
            logger.info(f"Сообщение помощи ID {message_id} успешно активировано.")
            return selected_message
        else:
            await db.rollback()
            logger.warning(f"Попытка активировать несуществующее сообщение помощи ID {message_id}.")
            return None


async def delete_help_message(message_id: int) -> bool:
    """
    Удаляет сообщение помощи из базы данных по ID.
    Возвращает True, если сообщение было успешно удалено, False в противном случае.
    """
    async with get_db_session() as db:
        message = await db.get(HelpMessage, message_id)
        if message:
            await db.delete(message)
            await db.commit()
            # Логирование без title
            logger.info(f"Сообщение помощи ID {message_id} успешно удалено из БД.")
            return True
        logger.warning(f"Попытка удалить несуществующее сообщение помощи ID {message_id}.")
        return False


async def get_all_help_messages() -> List[HelpMessage]:
    """
    Получает все сообщения помощи из базы данных, отсортированные по дате создания.
    """
    async with get_db_session() as db:
        query = select(HelpMessage).order_by(HelpMessage.created_at.desc()) # type: ignore [call-overload]
        result = await db.execute(query)
        messages = list(result.scalars().all())
        return messages
