# models.py
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

# Базовый класс для наших моделей SQLAlchemy
Base = declarative_base()

class Order(Base):
    """
    Модель для хранения информации о заказах.
    """
    __tablename__ = 'orders'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String)
    order_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())
    sent_at = Column(DateTime)
    received_at = Column(DateTime)
    status = Column(String, default='pending') # pending, processing, completed, cancelled
    full_name = Column(String)
    delivery_address = Column(String)
    payment_method = Column(String)
    contact_phone = Column(String)
    delivery_notes = Column(Text)

    def __repr__(self):
        return f"<Order(id={self.id}, user_id={self.user_id}, status='{self.status}')>"

class HelpMessage(Base):
    """
    Модель для хранения сообщений помощи.
    Админ может добавлять, редактировать, удалять эти сообщения
    и выбирать одно из них как активное.
    """
    __tablename__ = 'help_messages' # Обновленное название таблицы

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False, unique=True) # Название сообщения (например, "Общая помощь", "Доставка")
    message_text = Column(Text, nullable=False) # Сам текст сообщения помощи
    is_active = Column(Boolean, default=False) # Флаг: True, если это текущее активное сообщение
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<HelpMessage(id={self.id}, title='{self.title}', is_active={self.is_active})>"
