from datetime import datetime
from typing import Optional  # Импортируем Optional для type hints

from sqlalchemy import Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy.sql import func

# Базовый класс для наших моделей SQLAlchemy.
Base = declarative_base()


class User(Base):
    """
    Модель для хранения информации о пользователях бота и их настроек.

    Атрибуты:
        id (int): Уникальный идентификатор записи в таблице (первичный ключ, автоинкремент).
        user_id (int): Telegram ID пользователя (уникальный, не nullable).
        username (str, optional): Username пользователя Telegram.
        first_name (str, optional): Имя пользователя Telegram.
        last_name (str, optional): Фамилия пользователя Telegram.
        user_provided_full_name (str, optional): Полное имя (ФИО), введенное пользователем при оформлении заказа.
        user_provided_phone_number (str, optional): Контактный номер телефона, введенный пользователем.
        language_code (str): Выбранный язык локализации ('uk', 'ru', 'en'). По умолчанию 'uk'.
        notifications_enabled (bool): Флаг, указывающий, хочет ли пользователь получать уведомления. По умолчанию True.
        created_at (datetime): Дата и время первого взаимодействия пользователя с ботом.
        updated_at (datetime): Дата и время последнего обновления информации о пользователе.
    """
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True,
                                         index=True)  # Telegram User ID, уникальный и с индексом
    username: Mapped[Optional[str]] = mapped_column(String)
    first_name: Mapped[Optional[str]] = mapped_column(String)
    last_name: Mapped[Optional[str]] = mapped_column(String)
    user_provided_full_name: Mapped[Optional[str]] = mapped_column(String)  # ФИО из заказа
    # Изменено: phone_number вместо user_provided_phone_number, как в предоставленной версии
    phone_number: Mapped[Optional[str]] = mapped_column(String)  # Телефон из заказа
    language_code: Mapped[str] = mapped_column(String(5), default='uk',
                                               nullable=False)  # 'uk', 'ru', 'en', ограничение длины
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    # Изменено: last_activity_at вместо updated_at, как в предоставленной версии
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        """Представление объекта User для отладки."""
        return f"<User(id={self.id}, user_id={self.user_id}, username='{self.username}', lang='{self.language_code}')>"


class Order(Base):
    """
    Модель для хранения информации о заказах пользователя.

    Атрибуты:
        id (int): Уникальный идентификатор заказа (первичный ключ).
        user_id (int): Telegram ID пользователя, сделавшего заказ.
        username (str, optional): Username пользователя Telegram.
        order_text (str): Основной текст заказа.
        created_at (datetime): Дата и время создания заказа.
        sent_at (datetime, optional): Дата и время отправки заказа.
        received_at (datetime, optional): Дата и время получения заказа.
        status (str): Текущий статус заказа (например, 'new', 'pending', 'delivered').
        full_name (str, optional): Полное имя (ФИО) клиента.
        delivery_address (str, optional): Адрес доставки.
        payment_method (str, optional): Предпочитаемый способ оплаты.
        contact_phone (str, optional): Контактный номер телефона клиента.
        delivery_notes (str, optional): Дополнительные примечания к доставке.
    """
    __tablename__ = 'orders'

    # Использование mapped_column для явной типизации и Column для определения настроек
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False,
                                         index=True)  # Добавлен индекс для user_id для быстрого поиска
    username: Mapped[Optional[str]] = mapped_column(String)  # Optional для nullable полей
    order_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=func.now())  # timezone=True для хранения UTC
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default='new', index=True)  # Значение по умолчанию 'new' и индекс
    full_name: Mapped[Optional[str]] = mapped_column(String)
    delivery_address: Mapped[Optional[str]] = mapped_column(String)
    payment_method: Mapped[Optional[str]] = mapped_column(String)
    contact_phone: Mapped[Optional[str]] = mapped_column(String)
    delivery_notes: Mapped[Optional[str]] = mapped_column(Text)

    def __repr__(self) -> str:
        """Представление объекта Order для отладки."""
        return f"<Order(id={self.id}, user_id={self.user_id}, status='{self.status}')>"


class HelpMessage(Base):
    """
    Модель для хранения сообщений помощи, которые могут быть показаны пользователю.
    Админ может добавлять, редактировать, удалять эти сообщения и выбирать одно
    из них как активное (только одно сообщение может быть активным одновременно для каждого языка).

    Атрибуты:
        id (int): Уникальный идентификатор сообщения помощи (первичный ключ).
        message_text (str): Полный текст сообщения помощи.
        language_code (str): Код языка, к которому относится сообщение (например, 'uk', 'en', 'ru').
        is_active (bool): Флаг, указывающий, является ли это сообщение активным.
        created_at (datetime): Дата и время создания сообщения.
        updated_at (datetime): Дата и время последнего обновления сообщения.
    """
    __tablename__ = 'help_messages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Добавлено поле language_code
    language_code: Mapped[str] = mapped_column(String(10), nullable=False, default='uk', index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # Добавлен индекс для is_active
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # UniqueConstraint с sqlite_where был удален, так как он вызывал ошибку
    # и его функциональность по обеспечению уникальности активного сообщения
    # для каждого языка уже реализована на уровне приложения в db.py.

    def __repr__(self) -> str:
        """Представление объекта HelpMessage для отладки."""
        # Обновлено __repr__ для включения language_code
        return (f"<HelpMessage(id={self.id}, lang='{self.language_code}', "
                f"is_active={self.is_active}, text='{self.message_text[:50]}...')>")

