# database.py
import sqlite3
from datetime import datetime

DATABASE_NAME = 'orders.db'

def init_db():
    """Инициализирует базу данных, создает таблицу orders, если она не существует."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            order_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            received_at TEXT,
            status TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def add_order(user_id: int, username: str, order_text: str):
    """Добавляет новый заказ в базу данных."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    created_at = datetime.now().isoformat()
    status = "Новый" # Начальный статус заказа
    cursor.execute('''
        INSERT INTO orders (user_id, username, order_text, created_at, status)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, order_text, created_at, status))
    order_id = cursor.lastrowid # Получаем ID только что добавленного заказа
    conn.commit()
    conn.close()
    return order_id

def get_all_orders():
    """Возвращает все заказы из базы данных."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders ORDER BY created_at DESC')
    orders = cursor.fetchall()
    conn.close()
    return orders

def get_order_by_id(order_id: int):
    """Возвращает заказ по его ID."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
    order = cursor.fetchone()
    conn.close()
    return order

def update_order_status(order_id: int, new_status: str):
    """Обновляет статус заказа по его ID."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    # Обновляем также дату, если статус меняется на "Отправлен" или "Получен"
    update_field = ''
    if new_status == 'Отправлен':
        update_field = ', sent_at = ?'
        update_value = datetime.now().isoformat()
    elif new_status == 'Получен':
        update_field = ', received_at = ?'
        update_value = datetime.now().isoformat()
    else:
        update_value = None

    if update_field:
        cursor.execute(f'UPDATE orders SET status = ?{update_field} WHERE id = ?', (new_status, update_value, order_id))
    else:
        cursor.execute('UPDATE orders SET status = ? WHERE id = ?', (new_status, order_id))

    conn.commit()
    conn.close()

def search_orders(query: str):
    """Ищет заказы по ID или ключевым словам в тексте заказа."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    # Попробуем преобразовать запрос в число для поиска по ID
    try:
        order_id = int(query)
        cursor.execute('SELECT * FROM orders WHERE id = ? ORDER BY created_at DESC', (order_id,))
    except ValueError:
        # Если не число, ищем по тексту заказа
        cursor.execute('SELECT * FROM orders WHERE order_text LIKE ? ORDER BY created_at DESC', ('%' + query + '%',))
    orders = cursor.fetchall()
    conn.close()
    return orders

def update_order_text(order_id: int, new_text: str):
    """Обновляет текстовое сообщение заказа."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE orders SET order_text = ? WHERE id = ?', (new_text, order_id))
    conn.commit()
    conn.close()

def get_user_orders(user_id: int):
    """Возвращает все заказы конкретного пользователя."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    orders = cursor.fetchall()
    conn.close()
    return orders