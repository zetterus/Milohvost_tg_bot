# config.py
import os
from dotenv import load_dotenv # Эта строка позволяет читать .env файл

load_dotenv() # Загружаем переменные окружения из .env файла

# Настройки бота
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID администраторов
# os.getenv("ADMIN_IDS", "") - получает строку из .env.
# .split(',') - разделяет строку по запятым, получая список строк (например, ['682496357', '987654321']).
# map(int, ...) - преобразует каждую строку в целое число.
# list(...) - конвертирует результат map в обычный список.
# Если ADMIN_IDS нет в .env, то os.getenv вернет пустую строку, и list(map...) создаст пустой список, что безопасно.
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(',')))

# Настройки базы данных
DATABASE_NAME = os.getenv("DATABASE_NAME", "orders_bot.db") # Если DATABASE_NAME нет в .env, будет использоваться значение по умолчанию

# Настройки логирования (не конфиденциальные, могут оставаться в коде)
import logging
LOGGING_LEVEL = logging.INFO # Можно изменить на logging.DEBUG для более подробного логирования

ORDERS_PER_PAGE = int(os.getenv("ORDERS_PER_PAGE", 10)) # Показываем 10 заказов на странице по умолчанию
MAX_PREVIEW_TEXT_LENGTH = 30 # Максимальная длина текста заказа на кнопке

# Карта для отображения статусов заказов
# Ключ - системное имя статуса (однословное, без нижних подчеркиваний), Значение - красивое отображение для пользователя
ORDER_STATUS_MAP = {
    'new': 'Новый заказ 📝',
    'stockcheck': 'Проверяем наличие у поставщика 🔍',
    'confirmed': 'Наличие подтверждено, оплата 💰',
    'paid': 'Оплата получена ✅',
    'tosupplier': 'Передаем поставщику ➡️',
    'awaitingship': 'Ожидает отправки со склада 📦',
    'shipped': 'Отправлен со склада 🚚',
    'intransit': 'В пути к получателю 🛣️',
    'delivered': 'Доставлен 🎉',
    'cancelled': 'Отменен ❌',
    'onhold': 'Приостановлен ⏸️',
    'returned': 'Возвращен 🔙'
}

# Статусы, которые считаются "активными" для пользователя (показываются в его истории)
# Теперь используем новые, однословные ключи
ACTIVE_ORDER_STATUSES = [
    'new',
    'stockcheck',
    'confirmed',
    'paid',
    'tosupplier',
    'awaitingship',
    'shipped',
    'intransit',
    'pickup',
    'onhold'
]