from datetime import datetime
from typing import Optional  # Импортируем Optional для type hints

from sqlalchemy import Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy.sql import func

# Базовый класс для наших моделей SQLAlchemy.
Base = declarative_base()


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
    из них как активное (только одно сообщение может быть активным одновременно).

    Атрибуты:
        id (int): Уникальный идентификатор сообщения помощи (первичный ключ).
        message_text (str): Полный текст сообщения помощи.
        is_active (bool): Флаг, указывающий, является ли это сообщение активным.
        created_at (datetime): Дата и время создания сообщения.
        updated_at (datetime): Дата и время последнего обновления сообщения.
    """
    __tablename__ = 'help_messages'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # Добавлен индекс для is_active
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        """Представление объекта HelpMessage для отладки."""
        return f"<HelpMessage(id={self.id}, is_active={self.is_active})>"
