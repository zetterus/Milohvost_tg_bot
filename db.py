import logging
from typing import List, Optional, Tuple
from contextlib import asynccontextmanager

from sqlalchemy import select, func, or_, event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection

from config import DATABASE_NAME, LOGGING_LEVEL
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

# Создание асинхронной сессии
AsyncSessionLocal = sessionmaker(
    expire_on_commit=False,
    class_=AsyncSession,
    bind=engine
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """
    Устанавливает PRAGMA для SQLite для поддержки внешних ключей и пользовательской функции LOWER.
    """
    if isinstance(dbapi_connection, AsyncAdapt_aiosqlite_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # Регистрируем пользовательскую функцию LOWER для SQLite
        dbapi_connection.create_function("LOWER", 1, _sqlite_unicode_lower)
        cursor.close()


@asynccontextmanager
async def get_db_session():
    """
    Предоставляет асинхронную сессию базы данных.
    Используется как контекстный менеджер (async with).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Ошибка транзакции базы данных: {e}")
            await session.rollback()
            raise


# Функция create_tables_async больше не нужна для создания таблиц,
# так как это будет делать Alembic.
# Если она используется для чего-то еще, оставьте ее, но удалите вызов create_all.
async def create_tables_async():
    """
    Эта функция теперь может быть пустой или удалена,
    так как создание таблиц будет управляться Alembic.
    Если у вас есть другие инициализационные задачи, оставьте их здесь.
    """
    logger.info("Alembic управляет миграциями базы данных. create_tables_async() не выполняет создание таблиц.")
    pass  # Или удалите эту функцию, если она больше не нужна вовсе


# --- Функции для работы с пользователями ---

async def get_or_create_user(
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
) -> User:
    """
    Получает пользователя по user_id или создает нового, если он не существует.
    Обновляет username, first_name, last_name и last_activity_at при каждом обращении.
    """
    async with get_db_session() as db:
        stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # Обновляем данные пользователя, если они изменились
            user.username = username
            user.first_name = first_name
            user.last_name = last_name
            user.last_activity_at = func.now()  # Использование last_activity_at
            logger.debug(f"Пользователь {user_id} обновлен в БД.")
        else:
            # Создаем нового пользователя
            user = User(
                user_id=user_id,
                username=username,
                first_name=first_name,
                last_name=last_name
            )
            db.add(user)
            logger.info(f"Новый пользователь {user_id} добавлен в БД.")

        await db.flush()  # Убедимся, что user.id доступен, если это новый пользователь
        await db.refresh(user)  # Обновляем объект, чтобы получить актуальные данные
        return user


async def get_user_language_code(user_id: int) -> str:
    """
    Получает код языка пользователя из базы данных.
    Возвращает 'uk' (украинский) по умолчанию, если пользователь не найден.
    """
    async with get_db_session() as db:
        stmt = select(User.language_code).where(User.user_id == user_id)
        result = await db.execute(stmt)
        language_code = result.scalar_one_or_none()
        if language_code:
            return language_code
        return 'uk'  # Язык по умолчанию


async def update_user_language(user_id: int, new_language_code: str) -> Optional[User]:
    """
    Обновляет код языка для пользователя в базе данных.
    Возвращает обновленный объект User или None, если пользователь не найден.
    """
    async with get_db_session() as db:
        stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.language_code = new_language_code
            user.last_activity_at = func.now()  # Использование last_activity_at
            logger.info(f"Язык пользователя {user_id} обновлен на '{new_language_code}'.")
            return user
        logger.warning(f"Пользователь с ID {user_id} не найден для обновления языка.")
        return None


async def get_user_notifications_status(user_id: int) -> Optional[bool]:
    """
    Получает статус уведомлений пользователя из базы данных.
    Возвращает True/False или None, если пользователь не найден.
    """
    async with get_db_session() as db:
        # Исправлено: используем select().where() для поиска по user_id (Telegram ID)
        stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return user.notifications_enabled
        logger.warning(f"Пользователь с ID {user_id} не найден для получения статуса уведомлений.")
        return None


async def update_user_notifications_status(user_id: int, status: bool) -> Optional[User]:
    """
    Обновляет статус уведомлений пользователя в базе данных.
    Возвращает обновленный объект User или None, если пользователь не найден.
    """
    async with get_db_session() as db:
        # Исправлено: используем select().where() для поиска по user_id (Telegram ID)
        stmt = select(User).where(User.user_id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            user.notifications_enabled = status
            user.last_activity_at = func.now()
            logger.info(f"Статус уведомлений пользователя {user_id} обновлен на '{status}'.")
            return user
        logger.warning(f"Пользователь с ID {user_id} не найден для обновления статуса уведомлений.")
        return None


# --- Функции для работы с заказами ---

async def add_new_order(
        user_id: int,
        username: str,
        order_text: str,
        full_name: Optional[str] = None,
        delivery_address: Optional[str] = None,
        payment_method: Optional[str] = None,
        contact_phone: Optional[str] = None,
        delivery_notes: Optional[str] = None,
        status: str = 'new'
) -> Order:
    """
    Добавляет новый заказ в базу данных.
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
            status=status
        )
        db.add(new_order)
        await db.flush()  # Для получения ID нового заказа
        await db.refresh(new_order)  # Обновляем объект, чтобы получить актуальные данные (например, created_at)
        logger.info(f"Новый заказ ID {new_order.id} добавлен от пользователя {user_id}.")
        return new_order


async def get_order_by_id(order_id: int) -> Optional[Order]:
    """
    Получает заказ по его ID.
    """
    async with get_db_session() as db:
        stmt = select(Order).where(Order.id == order_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


async def update_order_status(order_id: int, new_status: str) -> bool:
    """
    Обновляет статус заказа по его ID.
    """
    async with get_db_session() as db:
        order = await db.get(Order, order_id)
        if order:
            order.status = new_status
            order.updated_at = func.now()
            logger.info(f"Статус заказа ID {order_id} обновлен на '{new_status}'.")
            return True
        logger.warning(f"Попытка обновить статус несуществующего заказа ID {order_id}.")
        return False


async def update_order_text(order_id: int, new_text: str) -> bool:
    """
    Обновляет текст заказа по его ID.
    """
    async with get_db_session() as db:
        order = await db.get(Order, order_id)
        if order:
            order.order_text = new_text
            order.updated_at = func.now()
            logger.info(f"Текст заказа ID {order_id} обновлен.")
            return True
        logger.warning(f"Попытка обновить текст несуществующего заказа ID {order_id}.")
        return False


async def delete_order(order_id: int) -> bool:
    """
    Удаляет заказ из базы данных по ID.
    """
    async with get_db_session() as db:
        order = await db.get(Order, order_id)
        if order:
            await db.delete(order)
            logger.info(f"Заказ ID {order_id} успешно удален из БД.")
            return True
        logger.warning(f"Попытка удалить несуществующий заказ ID {order_id}.")
        return False


async def get_all_orders(offset: int = 0, limit: int = 10) -> Tuple[List[Order], int]:
    """
    Получает все заказы из базы данных с пагинацией, отсортированные по дате создания в убывающем порядке.
    Возвращает список заказов и общее количество заказов.
    """
    async with get_db_session() as db:
        # Запрос для получения общего количества заказов
        count_stmt = select(func.count()).select_from(Order)
        total_orders = (await db.execute(count_stmt)).scalar_one()

        # Запрос для получения заказов с пагинацией
        stmt = select(Order).order_by(Order.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(stmt)
        orders = result.scalars().all()
        return orders, total_orders


async def search_orders(search_query: str, offset: int = 0, limit: int = 10) -> Tuple[List[Order], int]:
    """
    Ищет заказы по ID, части username или части текста заказа.
    Поиск по тексту и username регистронезависимый.
    Возвращает список найденных заказов и их общее количество.
    """
    async with get_db_session() as db:
        search_pattern = f"%{search_query.lower()}%"
        try:
            # Попытка преобразовать search_query в int для поиска по ID
            search_id = int(search_query)
        except ValueError:
            search_id = None

        # Базовый запрос для подсчета
        count_stmt = select(func.count()).select_from(Order)
        # Базовый запрос для данных
        data_stmt = select(Order)

        conditions = []

        if search_id is not None:
            conditions.append(Order.id == search_id)

        # Добавляем условия для текстового поиска, используя LOWER для регистронезависимости
        # Используем func.lower() для совместимости с SQLAlchemy
        conditions.append(func.lower(Order.username).like(search_pattern))
        conditions.append(func.lower(Order.order_text).like(search_pattern))
        conditions.append(func.lower(Order.full_name).like(search_pattern))
        conditions.append(func.lower(Order.delivery_address).like(search_pattern))
        conditions.append(func.lower(Order.contact_phone).like(search_pattern))
        conditions.append(func.lower(Order.delivery_notes).like(search_pattern))

        # Комбинируем условия с OR
        combined_condition = or_(*conditions)

        # Применяем условие к запросам
        count_stmt = count_stmt.where(combined_condition)
        data_stmt = data_stmt.where(combined_condition)

        # Выполняем подсчет
        total_orders = (await db.execute(count_stmt)).scalar_one()

        # Выполняем запрос данных с сортировкой и пагинацией
        data_stmt = data_stmt.order_by(Order.created_at.desc()).offset(offset).limit(limit)
        result = await db.execute(data_stmt)
        orders = result.scalars().all()

        return orders, total_orders


async def get_user_orders_paginated(user_id: int, offset: int = 0, limit: int = 5) -> List[Order]:
    """
    Получает заказы конкретного пользователя с пагинацией, отсортированные по дате создания в убывающем порядке.
    """
    async with get_db_session() as db:
        stmt = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).offset(offset).limit(
            limit)
        result = await db.execute(stmt)
        return result.scalars().all()


async def count_user_orders(user_id: int) -> int:
    """
    Подсчитывает общее количество заказов конкретного пользователя.
    """
    async with get_db_session() as db:
        stmt = select(func.count()).where(Order.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one()


# --- Функции для работы с сообщениями помощи ---

async def add_help_message(message_text: str, language_code: str, is_active: bool = False) -> HelpMessage:
    """
    Добавляет новое сообщение помощи в базу данных.
    Если is_active=True, деактивирует все другие активные сообщения для этого языка.
    """
    async with get_db_session() as db:
        if is_active:
            # Деактивируем все текущие активные сообщения для этого языка
            active_messages = (await db.execute(
                select(HelpMessage).where(HelpMessage.language_code == language_code, HelpMessage.is_active == True)
            )).scalars().all()
            for msg in active_messages:
                msg.is_active = False
            await db.flush()
            logger.info(f"Все активные сообщения помощи для языка '{language_code}' деактивированы.")

        new_message = HelpMessage(
            message_text=message_text,
            language_code=language_code,
            is_active=is_active
        )
        db.add(new_message)
        await db.flush()
        logger.info(f"Новое сообщение помощи ID {new_message.id} для языка '{language_code}' добавлено в БД.")
        return new_message


async def get_help_message_by_id(message_id: int) -> Optional[HelpMessage]:
    """
    Получает сообщение помощи по его ID.
    """
    async with get_db_session() as db:
        stmt = select(HelpMessage).where(HelpMessage.id == message_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


async def get_active_help_message_from_db(language_code: str) -> Optional[HelpMessage]:
    """
    Получает активное сообщение помощи для указанного языка из базы данных.
    """
    async with get_db_session() as db:
        stmt = select(HelpMessage).where(HelpMessage.is_active == True, HelpMessage.language_code == language_code)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


async def set_active_help_message(message_id: int, language_code: str) -> Optional[HelpMessage]:
    """
    Устанавливает сообщение помощи с заданным ID как активное для указанного языка.
    Деактивирует все другие активные сообщения для этого языка.
    Возвращает активированное сообщение или None, если сообщение не найдено или язык не совпадает.
    """
    async with get_db_session() as db:
        try:
            selected_message = await db.get(HelpMessage, message_id)
            if not selected_message:
                logger.warning(
                    f"Попытка активировать несуществующее сообщение помощи ID {message_id}. Транзакция отменена.")
                return None

            # Проверяем, что сообщение относится к тому же языку, который мы пытаемся активировать
            if selected_message.language_code != language_code:
                logger.warning(
                    f"Попытка активировать сообщение ID {message_id} для языка '{language_code}', "
                    f"но сообщение имеет язык '{selected_message.language_code}'. Отмена операции."
                )
                return None

            # Деактивируем все текущие активные сообщения для этого языка
            active_messages = (await db.execute(
                select(HelpMessage).where(HelpMessage.language_code == language_code, HelpMessage.is_active == True)
            )).scalars().all()
            for msg in active_messages:
                msg.is_active = False
            await db.flush()

            selected_message.is_active = True
            selected_message.updated_at = func.now()
            logger.info(f"Сообщение помощи ID {message_id} для языка '{language_code}' успешно активировано.")
            return selected_message
        except Exception as e:
            await db.rollback()
            logger.error(f"Ошибка при установке активного сообщения помощи ID {message_id}: {e}. Транзакция отменена.")
            raise


async def deactivate_help_message(message_id: int) -> bool:
    """
    Деактивирует сообщение помощи по его ID.
    Возвращает True, если сообщение было успешно деактивировано, False в противном случае.
    """
    async with get_db_session() as db:
        message = await db.get(HelpMessage, message_id)
        if message:
            message.is_active = False
            message.updated_at = func.now()
            logger.info(f"Сообщение помощи ID {message_id} деактивировано.")
            return True
        logger.warning(f"Попытка деактивировать несуществующее сообщение помощи ID {message_id}.")
        return False


async def delete_help_message(message_id: int) -> bool:
    """
    Удаляет сообщение помощи из базы данных по ID.
    Возвращает True, если сообщение было успешно удалено, False в противном случае.
    """
    async with get_db_session() as db:
        message = await db.get(HelpMessage, message_id)
        if message:
            await db.delete(message)
            logger.info(f"Сообщение помощи ID {message_id} успешно удалено из БД.")
            return True
        logger.warning(f"Попытка удалить несуществующий заказ ID {message_id}.")
        return False


async def get_all_help_messages(language_code: Optional[str] = None) -> List[HelpMessage]:
    """
    Получает все сообщения помощи из базы данных, отсортированные по дате создания в убывающем порядке.
    Можно отфильтровать по language_code.
    """
    async with get_db_session() as db:
        stmt = select(HelpMessage).order_by(HelpMessage.created_at.desc())
        if language_code:
            stmt = stmt.where(HelpMessage.language_code == language_code)
        result = await db.execute(stmt)
        return result.scalars().all()


async def update_help_message_language(message_id: int, new_language_code: str) -> Optional[HelpMessage]:
    """
    Обновляет язык сообщения помощи по его ID.
    Если сообщение было активно для старого языка, оно остается активным для нового языка,
    при этом деактивируются другие активные сообщения для нового языка.
    """
    async with get_db_session() as db:
        message = await db.get(HelpMessage, message_id)
        if message:
            old_language_code = message.language_code
            is_currently_active = message.is_active

            # Если сообщение было активно, деактивируем все активные для нового языка
            if is_currently_active:
                active_messages_for_new_lang = (await db.execute(
                    select(HelpMessage).where(HelpMessage.language_code == new_language_code,
                                              HelpMessage.is_active == True)
                )).scalars().all()
                for msg in active_messages_for_new_lang:
                    msg.is_active = False
                await db.flush()  # Применяем изменения перед обновлением текущего сообщения

            message.language_code = new_language_code
            message.updated_at = func.now()
            # Если сообщение было активно, оно остается активным для нового языка
            # Если не было активно, остается неактивным.
            message.is_active = is_currently_active  # Сохраняем статус активности

            logger.info(
                f"Язык сообщения помощи ID {message_id} изменен с '{old_language_code}' на '{new_language_code}'.")
            return message
        logger.warning(f"Попытка обновить язык несуществующего сообщения помощи ID {message_id}.")
        return None
