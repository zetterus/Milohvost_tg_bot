# database.py

import sqlite3
from datetime import datetime

DATABASE_NAME = 'orders.db'


def init_db():
    """Инициализирует базу данных, создает таблицу orders, если она не существует."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       CREATE TABLE IF NOT EXISTS orders
                       (
                           id
                           INTEGER
                           PRIMARY
                           KEY
                           AUTOINCREMENT,
                           user_id
                           INTEGER
                           NOT
                           NULL,
                           username
                           TEXT,
                           order_text
                           TEXT
                           NOT
                           NULL,
                           created_at
                           TEXT
                           NOT
                           NULL,
                           sent_at
                           TEXT,
                           received_at
                           TEXT,
                           status
                           TEXT
                           NOT
                           NULL,
                           -- Новые поля для доставки
                           full_name
                           TEXT,
                           delivery_address
                           TEXT,
                           payment_method
                           TEXT,
                           contact_phone
                           TEXT,
                           delivery_notes
                           TEXT
                       )
                       ''')
        # Добавление новых столбцов, если они еще не существуют
        # Это нужно, чтобы не удалять старую таблицу при каждом запуске
        add_column_if_not_exists(cursor, 'orders', 'full_name', 'TEXT')
        add_column_if_not_exists(cursor, 'orders', 'delivery_address', 'TEXT')
        add_column_if_not_exists(cursor, 'orders', 'payment_method', 'TEXT')
        add_column_if_not_exists(cursor, 'orders', 'contact_phone', 'TEXT')
        add_column_if_not_exists(cursor, 'orders', 'delivery_notes', 'TEXT')
        conn.commit()


def add_column_if_not_exists(cursor, table_name, column_name, column_type):
    """Добавляет колонку, если она не существует."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [col[1] for col in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def add_order(user_id, username, order_text, full_name=None, delivery_address=None,
              payment_method=None, contact_phone=None, delivery_notes=None):
    """Добавляет новый заказ в базу данных."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        created_at = datetime.now().isoformat()
        status = "Новый"
        cursor.execute('''
                       INSERT INTO orders (user_id, username, order_text, created_at, status,
                                           full_name, delivery_address, payment_method, contact_phone, delivery_notes)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (user_id, username, order_text, created_at, status,
                             full_name, delivery_address, payment_method, contact_phone, delivery_notes))
        conn.commit()
        return cursor.lastrowid


def get_all_orders():
    """Возвращает все заказы из базы данных."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders ORDER BY created_at DESC')
        return cursor.fetchall()


def get_order_by_id(order_id):
    """Возвращает заказ по его ID."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        return cursor.fetchone()


def get_user_orders(user_id):
    """Возвращает все заказы конкретного пользователя."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
        return cursor.fetchall()


def update_order_status(order_id, status):
    """Обновляет статус заказа по его ID."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # Обновляем sent_at или received_at в зависимости от статуса
        if status == "Отправлен":
            cursor.execute('UPDATE orders SET status = ?, sent_at = ? WHERE id = ?',
                           (status, datetime.now().isoformat(), order_id))
        elif status == "Получен":
            cursor.execute('UPDATE orders SET status = ?, received_at = ? WHERE id = ?',
                           (status, datetime.now().isoformat(), order_id))
        else:
            cursor.execute('UPDATE orders SET status = ? WHERE id = ?', (status, order_id))
        conn.commit()


def update_order_text(order_id, new_text):
    """Обновляет текстовое сообщение заказа."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE orders SET order_text = ? WHERE id = ?', (new_text, order_id))
        conn.commit()


def update_order_delivery_info(order_id, full_name=None, delivery_address=None,
                               payment_method=None, contact_phone=None, delivery_notes=None):
    """Обновляет способ доставки заказа по его ID."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # Строим SET часть запроса динамически
        update_fields = []
        params = []
        if full_name is not None:
            update_fields.append("full_name = ?")
            params.append(full_name)
        if delivery_address is not None:
            update_fields.append("delivery_address = ?")
            params.append(delivery_address)
        if payment_method is not None:
            update_fields.append("payment_method = ?")
            params.append(payment_method)
        if contact_phone is not None:
            update_fields.append("contact_phone = ?")
            params.append(contact_phone)
        if delivery_notes is not None:
            update_fields.append("delivery_notes = ?")
            params.append(delivery_notes)

        if not update_fields:
            return  # Ничего обновлять

        query = f"UPDATE orders SET {', '.join(update_fields)} WHERE id = ?"
        params.append(order_id)

        cursor.execute(query, tuple(params))
        conn.commit()


def search_orders(query):
    """Ищет заказы по ID или ключевым словам в тексте заказа."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # Поиск по ID заказа (если запрос - число) или по тексту заказа/имени пользователя
        try:
            order_id = int(query)
            cursor.execute('SELECT * FROM orders WHERE id = ? ORDER BY created_at DESC', (order_id,))
        except ValueError:
            search_query = f'%{query}%'
            cursor.execute('''
                           SELECT *
                           FROM orders
                           WHERE order_text LIKE ?
                              OR username LIKE ?
                              OR full_name LIKE ?
                              OR delivery_address LIKE ?
                           ORDER BY created_at DESC
                           ''', (search_query, search_query, search_query, search_query))
        return cursor.fetchall()


def delete_order(order_id):
    """Удаляет заказ по его ID."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
        conn.commit()
