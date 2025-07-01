import os
import logging
import re  # Импортируем re для использования регулярных выражений

from dotenv import load_dotenv

load_dotenv()

# --- Настройки бота ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID администраторов
# ADMIN_IDS: список целых чисел, представляющих Telegram ID администраторов.
# Если переменная окружения ADMIN_IDS не установлена или пуста, список будет пустым.
ADMIN_IDS = list(map(int, filter(None, os.getenv("ADMIN_IDS", "").split(','))))

# --- Настройки базы данных ---
DATABASE_NAME = os.getenv("DATABASE_NAME", "orders_bot.db")

# --- Настройки логирования ---
LOGGING_LEVEL = logging.INFO  # Уровень логирования: INFO, DEBUG, WARNING, ERROR, CRITICAL

# --- Настройки отображения заказов ---
ORDERS_PER_PAGE = int(os.getenv("ORDERS_PER_PAGE", 10))  # Количество заказов на одной странице в пагинации
MAX_PREVIEW_TEXT_LENGTH = int(
    os.getenv("MAX_PREVIEW_TEXT_LENGTH", 30))  # Максимальная длина текста заказа для предпросмотра

# --- Карта для отображения статусов заказов ---
# Ключ: системное имя статуса (однословное).
# Значение: дружелюбное отображение для пользователя.
ORDER_STATUS_MAP = {
    'new': 'Новый заказ 📝',
    'stockcheck': 'Проверяем наличие у поставщика 🔍',
    'confirmed': 'Наличие подтверждено, оплата 💰',
    'paid': 'Оплата получена ✅',
    'tosupplier': 'Передаем поставщику ➡️',
    'awaitingship': 'Ожидает отправки со склада 📦',
    'shipped': 'Отправлен со склада 🚚',
    'intransit': 'В пути к получателю 🛣️',
    'onhold': 'Приостановлен ⏸️',
    'delivered': 'Доставлен 🎉',
    'cancelled': 'Отменен ❌',
    'returned': 'Возвращен 🔙'
}

# Статусы, которые считаются "активными" для пользователя (показываются в его истории заказов)
ACTIVE_ORDER_STATUSES = [
    'new',
    'stockcheck',
    'confirmed',
    'paid',
    'tosupplier',
    'awaitingship',
    'shipped',
    'intransit',
    'onhold',
]

# Отображаемые названия полей заказа для пользователя
DISPLAY_FIELD_NAMES = {
    'order_text': 'текст заказа',
    'full_name': 'полное имя',
    'delivery_address': 'адрес доставки',
    'payment_method': 'способ оплаты',
    'contact_phone': 'контактный телефон',
    'delivery_notes': 'примечания к доставке'
}

# Регулярное выражение для номера телефона
# ^ - начало строки
# \+? - необязательный знак "+" (ноль или одно вхождение)
# \d{10,11} - ровно 10 или 11 цифр
# $ - конец строки
PHONE_NUMBER_REGEX = re.compile(r"^\+?\d{11,12}$")

# --- Конфигурация полей для оформления заказа ---
# Это централизованное описание порядка полей, их подсказок,
# соответствующего FSM-состояния и типа ввода.
# 'next_field' должен соответствовать 'key' следующего поля или быть 'final_confirm'
ORDER_FIELDS_CONFIG = [
    {
        "key": "order_text",
        "prompt": "Введите заказ: 📝",
        "state_name": "waiting_for_order_text",
        "next_field": "full_name",
        "input_type": "text"
    },
    {
        "key": "full_name",
        "prompt": "Теперь введи своё **полное имя** (ФИО) 👤:",
        "state_name": "waiting_for_full_name",
        "next_field": "delivery_address",
        "input_type": "text"
    },
    {
        "key": "delivery_address",
        "prompt": "Укажи **адрес доставки** (город, улица, дом, квартира) 🏠:",
        "state_name": "waiting_for_delivery_address",
        "next_field": "payment_method",
        "input_type": "text"
    },
    {
        "key": "payment_method",
        "prompt": "Как ты предпочитаешь **оплатить заказ**? 💳",
        "state_name": "waiting_for_payment_method",
        "next_field": "contact_phone",
        "input_type": "buttons",
        "options": {
            "Наличные 💰": "Наличные",
            "Картой при получении 💳": "Картой при получении"
        }
    },
    {
        "key": "contact_phone",
        "prompt": (
            "Пожалуйста, введите ваш **контактный телефон** или нажмите кнопку ниже, чтобы отправить его автоматически. "
            "Формат: `+<код страны><номер>` (например, `+380991234567`, `380998644567`, `80991238947` или `+12125550123`)."
        ),
        "state_name": "waiting_for_contact_phone",
        "next_field": "delivery_notes",
        "input_type": "contact_button"
    },
    {
        "key": "delivery_notes",
        "prompt": "Если есть **примечания к доставке** (например, 'домофон 123'), напиши их. Если нет, можешь отправить `-` или `нет` 💬:",
        "state_name": "waiting_for_delivery_notes",
        "next_field": "final_confirm",
        "input_type": "text"
    }
]

# Для быстрого доступа к конфигурации поля по его ключу
ORDER_FIELD_MAP = {field["key"]: field for field in ORDER_FIELDS_CONFIG}
