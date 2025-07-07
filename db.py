import logging
from typing import List, Optional, Tuple
from contextlib import asynccontextmanager
from datetime import datetime

from sqlalchemy import text, select, func, or_, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection

from aiogram.fsm.storage.base import BaseStorage, StorageKey

from config import DATABASE_NAME, LOGGING_LEVEL, ACTIVE_ORDER_STATUS_KEYS # <-- ИСПРАВЛЕНО: ACTIVE_ORDER_STATUSES на ACTIVE_ORDER_STATUS_KEYS
from models import Base, Order, HelpMessage, User

# Настройка логирования
logging.basicConfig(level=LOGGING_LEVEL)
logger = logging.getLogger(__name__)


# Пользовательская функция LOWER для SQLite с поддержкой Unicode
def _sqlite_unicode_lower(value: str | None) -> str | None:
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
    echo=False,  # Установите в True, чтобы видеть сгенерированные SQL-запросы в консоли
    pool_pre_ping=True  # Проверяет соединение перед использованием из пула
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
        logger.error(
            f"Слушатель событий получил неожиданный тип DBAPI-соединения: {type(dbapi_connection)}. Ожидается AsyncAdapt_aiosqlite_connection.")


# Асинхронная фабрика сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Объекты не истекают после коммита
    autocommit=False,  # Отключение автокоммита
    autoflush=False  # Отключение автофлаша
)


@asynccontextmanager
async def get_db_session() -> AsyncSession:  # Уточнен тип возвращаемого значения
    """
    Асинхронный генератор для получения сессии базы данных.
    Используется как асинхронный контекстный менеджер.
    Гарантирует закрытие сессии после использования.
    """
    db: AsyncSession = AsyncSessionLocal()
    try:
        yield db
    except Exception as e:
        await db.rollback()  # Откатываем транзакцию при ошибке
        logger.error(f"Ошибка в сессии базы данных, выполнен откат: {e}")
        raise  # Повторно выбрасываем исключение
    finally:
        await db.close()


async def create_tables_async() -> None:
    """
    Создает таблицы базы данных асинхронно, если они еще не существуют.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info(
        f"База данных '{DATABASE_NAME}' и таблицы успешно созданы/обновлены с использованием SQLAlchemy (асинхронно).")


# --- НОВЫЕ ФУНКЦИИ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ---

async def get_or_create_user(
    user_id: int,
    username: Optional[str] = None,
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    storage_key: Optional[StorageKey] = None,
    storage_obj: Optional['BaseStorage'] = None
    ) -> User:
    """
    Получает пользователя из базы данных по user_id.
    Если пользователь не найден, создает новую запись с данными из Telegram
    и языком по умолчанию 'uk'.
    Обновляет last_activity_at при каждом вызове.
    Также кэширует язык пользователя в Storage, если предоставлен storage_obj.
    """
    async with get_db_session() as db:
        user = await db.scalar(select(User).where(User.user_id == user_id))

        if user is None:
            new_user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
                language_code='uk',
                notifications_enabled=True,
            )
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            user = new_user
            logger.info(f"Новый пользователь ID {user_id} добавлен в БД.")
        else:
            await db.commit()
            await db.refresh(user)
            logger.debug(f"Пользователь ID {user_id} получен из БД (язык: {user.language_code}). Активность обновлена.")

        # --- ОБНОВЛЕНИЕ КЭША В STORAGE ---
        if storage_obj and storage_key:
            user_storage_data = await storage_obj.get_data(
                key=storage_key
            )

            if user_storage_data.get('lang') != user.language_code:
                user_storage_data['lang'] = user.language_code
                await storage_obj.set_data(
                    key=storage_key, data=user_storage_data
                )
                logger.debug(f"Язык пользователя {user_id} кэширован в Storage: {user.language_code}")
        # --- КОНЕЦ ОБНОВЛЕНИЯ КЭША ---

        return user


async def get_user_language_code(user_id: int, storage_key: Optional[StorageKey] = None,
                                 storage_obj: Optional['BaseStorage'] = None) -> str:
    """
    Получает код языка для пользователя. Сначала пытается получить из Storage,
    затем из базы данных. Если пользователь не найден, возвращает 'uk' по умолчанию.
    """
    # Сначала пробуем получить из кэша (Storage)
    if storage_obj and storage_key:
        user_storage_data = await storage_obj.get_data(
            key=storage_key
        )
        if 'lang' in user_storage_data:
            logger.debug(f"Язык для пользователя {user_id} получен из Storage: {user_storage_data['lang']}")
            return user_storage_data['lang']

    # Если в кэше нет или storage_obj не предоставлен, обращаемся к БД
    async with get_db_session() as db:
        user_lang = await db.scalar(select(User.language_code).where(User.user_id == user_id))
        if user_lang:
            logger.debug(f"Язык для пользователя {user_id} получен из БД: {user_lang}")
            if storage_obj and storage_key:
                user_storage_data = await storage_obj.get_data(
                    key=storage_key
                )
                user_storage_data['lang'] = user_lang
                await storage_obj.set_data(
                    key=storage_key, data=user_storage_data
                )
            return user_lang

        logger.warning(f"Язык для пользователя ID {user_id} не найден в БД и кэше, возвращается 'uk' по умолчанию.")
        return 'uk'


async def update_user_language(user_id: int, new_language_code: str, storage_key: Optional[StorageKey] = None,
                               storage_obj: Optional['BaseStorage'] = None) -> Optional[User]:
    """
    Обновляет предпочитаемый язык пользователя в базе данных и в Storage.
    """
    async with get_db_session() as db:
        user = await db.scalar(select(User).where(User.user_id == user_id))
        if user:
            user.language_code = new_language_code
            await db.commit()
            await db.refresh(user)
            logger.info(f"Язык пользователя ID {user_id} обновлен на '{new_language_code}'.")

            # Обновляем кэш в Storage
            if storage_obj and storage_key:
                user_storage_data = await storage_obj.get_data(
                    key=storage_key
                )
                user_storage_data['lang'] = new_language_code
                await storage_obj.set_data(
                    key=storage_key, data=user_storage_data
                )
                logger.debug(f"Язык пользователя {user_id} обновлен в Storage: {new_language_code}")

            return user
        logger.warning(f"Попытка обновить язык несуществующего пользователя ID {user_id}.")
        return None


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
        logger.info(f"Заказ ID {new_order.id} успешно добавлен в БД пользователем {user_id}.")
        return new_order


async def get_all_orders(offset: int = 0, limit: Optional[int] = None) -> Tuple[List[Order], int]:
    """
    Получает все заказы из базы данных с пагинацией и общее количество.
    Заказы сортируются по дате создания в убывающем порядке.

    :param offset: Смещение для пагинации (количество пропускаемых записей).
    :param limit: Максимальное количество заказов для возврата на одной странице.
    :return: Кортеж: (список объектов Order, общее количество заказов).
    """
    async with get_db_session() as db:
        # Получаем общее количество заказов
        total_orders_query = select(func.count(Order.id))
        total_orders = (await db.scalar(total_orders_query)) or 0

        # Получаем заказы с учетом пагинации
        orders_query = select(Order).order_by(Order.created_at.desc())
        if limit is not None:
            orders_query = orders_query.offset(offset).limit(limit)

        result = await db.execute(orders_query)
        orders = list(result.scalars().all())

        return orders, total_orders


async def get_user_orders_paginated(user_id: int, offset: int, limit: int) -> List[Order]:
    """
    Получает АКТИВНЫЕ заказы конкретного пользователя с пагинацией.
    Заказы сортируются по дате создания в убывающем порядке.

    :param user_id: ID пользователя.
    :param offset: Смещение (количество пропускаемых записей).
    :param limit: Максимальное количество записей для возврата (количество на странице).
    :return: Список объектов Order.
    """
    async with get_db_session() as db:
        stmt = (
            select(Order)
            .where(
                Order.user_id == user_id,
                Order.status.in_(ACTIVE_ORDER_STATUS_KEYS) # <-- ИСПРАВЛЕНО
            )
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


async def count_user_orders(user_id: int) -> int:
    """
    Считает общее количество АКТИВНЫХ заказов для конкретного пользователя.
    """
    async with get_db_session() as db:
        stmt = (
            select(func.count(Order.id))
            .where(
                Order.user_id == user_id,
                Order.status.in_(ACTIVE_ORDER_STATUS_KEYS) # <-- ИСПРАВЛЕНО
            )
        )
        total_orders = (await db.scalar(stmt))
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


async def search_orders(search_query: str, offset: int = 0, limit: Optional[int] = None) -> Tuple[
    List[Order], int]:
    """
    Ищет заказы по user_id, ID заказа, части имени пользователя или части текста заказа.
    Поддерживает пагинацию и возвращает общее количество найденных заказов.
    Поиск выполняется без учета регистра.

    :param search_query: Поисковый запрос пользователя.
    :param offset: Смещение для пагинации (количество пропускаемых записей).
    :param limit: Максимальное количество записей для возврата на одной странице.
    :return: Кортеж: (список объектов Order, общее количество найденных заказов без учета пагинации).
    """
    async with get_db_session() as db:
        search_query_stripped = search_query.strip()
        search_pattern = f"%{search_query_stripped.lower()}%"

        conditions = []

        # Поиск по числовым ID (user_id или order.id)
        try:
            numeric_query_value = int(search_query_stripped)
            conditions.append(or_(
                Order.user_id == numeric_query_value,
                Order.id == numeric_query_value
            ))
        except ValueError:
            pass

        # Поиск по строковым полям (username и order_text)
        if search_query_stripped:
            conditions.append(func.lower(Order.username).like(search_pattern))
            conditions.append(func.lower(Order.order_text).like(search_pattern))

        # Если ни одно условие не сформировано, значит, нет смысла искать
        if not conditions:
            logger.warning(f"Пустой список условий для поиска: '{search_query_stripped}'")
            return [], 0

        # Запрос для подсчета общего количества найденных заказов
        count_stmt = select(func.count(Order.id)).where(or_(*conditions))
        total_orders = (await db.scalar(count_stmt)) or 0

        # Запрос для получения списка заказов с пагинацией
        stmt = select(Order).where(or_(*conditions)).order_by(Order.created_at.desc())
        if limit is not None:
            stmt = stmt.offset(offset).limit(limit)

        try:
            logger.debug(
                f"Выполняется SQL-запрос для поиска (пагинация): {stmt.compile(engine, compile_kwargs={'literal_binds': True})}")
            result = await db.execute(stmt)
            orders = list(result.scalars().all())
            logger.info(f"Найдено {len(orders)} заказов по запросу: '{search_query_stripped}' (всего: {total_orders}).")
            return orders, total_orders
        except Exception as e:
            logger.error(f"Ошибка при поиске заказов в БД по запросу '{search_query_stripped}': {e}")
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

async def add_help_message(message_text: str, is_active: bool = False) -> HelpMessage:
    """
    Добавляет новое сообщение помощи в базу данных.
    Если is_active=True, деактивирует все остальные сообщения перед добавлением.
    """
    async with get_db_session() as db:
        if is_active:
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
        stmt = select(HelpMessage).where(HelpMessage.is_active == True).limit(1)
        active_message = await db.scalar(stmt)
        return active_message


async def set_active_help_message(message_id: int) -> Optional[HelpMessage]:
    """
    Устанавливает сообщение с указанным ID как активное, деактивируя все остальные.
    Возвращает активированное сообщение или None, если оно не найдено.
    Операция выполняется в рамках одной транзакции.
    """
    async with get_db_session() as db:
        try:
            await db.execute(
                text("UPDATE help_messages SET is_active = :false WHERE is_active = :true"),
                {"false": False, "true": True}
            )
            logger.debug("Все предыдущие активные сообщения помощи деактивированы.")

            selected_message = await db.get(HelpMessage, message_id)
            if selected_message:
                selected_message.is_active = True
                selected_message.updated_at = datetime.now()
                await db.commit()
                await db.refresh(selected_message)
                logger.info(f"Сообщение помощи ID {message_id} успешно активировано.")
                return selected_message
            else:
                await db.rollback()
                logger.warning(
                    f"Попытка активировать несуществующее сообщение помощи ID {message_id}. Транзакция отменена.")
                return None
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка при установке активного сообщения помощи ID {message_id}: {e}. Транзакция отменена.")
            raise


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
            logger.info(f"Сообщение помощи ID {message_id} успешно удалено из БД.")
            return True
        logger.warning(f"Попытка удалить несуществующее сообщение помощи ID {message_id}.")
        return False


async def get_all_help_messages() -> List[HelpMessage]:
    """
    Получает все сообщения помощи из базы данных, отсортированные по дате создания в убывающем порядке.
    """
    async with get_db_session() as db:
        stmt = select(HelpMessage).order_by(HelpMessage.created_at.desc())
        result = await db.execute(stmt)
        messages = list(result.scalars().all())
        return messages
