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

# --- Системные ключи для статусов заказов ---
# Эти ключи будут использоваться для получения локализованных названий из JSON.
# 'ORDER_STATUS_MAP' удален, так как его содержимое теперь в локализациях.
ORDER_STATUS_KEYS = [ # Переименовал для ясности
    'new',
    'stockcheck',
    'confirmed',
    'paid',
    'tosupplier',
    'awaitingship',
    'shipped',
    'intransit',
    'onhold',
    'delivered',
    'cancelled',
    'returned'
]

# Статусы, которые считаются "активными" для пользователя (показываются в его истории заказов)
# Оставляем только системные ключи
ACTIVE_ORDER_STATUS_KEYS = [ # Переименовал для ясности
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

# Системные ключи для названий полей заказа (теперь DISPLAY_FIELD_NAMES удален)
ORDER_FIELD_NAMES_KEYS = {
    'order_text': 'field_name_order_text',
    'full_name': 'field_name_full_name',
    'delivery_address': 'field_name_delivery_address',
    'payment_method': 'field_name_payment_method',
    'contact_phone': 'field_name_contact_phone',
    'delivery_notes': 'field_name_delivery_notes'
}


# Регулярное выражение для номера телефона
# ^ - начало строки
# \+? - необязательный знак "+" (ноль или одно вхождение)
# \d{10,12} - от 10 до 12 цифр (с учетом кода страны, например +38099...)
# $ - конец строки
PHONE_NUMBER_REGEX = re.compile(r"^\+?\d{10,12}$") # Изменил с 11,12 на 10,12, так как +380991234567 - это 12 цифр.
                                                 # Если номер без плюса (например 80991234567), то 11.
                                                 # Если вы хотите более строгую валидацию, её нужно будет доработать.

# --- Конфигурация полей для оформления заказа ---
# Это централизованное описание порядка полей, их подсказок,
# соответствующего FSM-состояния и типа ввода.
# 'next_field' должен соответствовать 'key' следующего поля или быть 'final_confirm'
ORDER_FIELDS_CONFIG = [
    {
        "key": "order_text",
        "prompt_key": "prompt_order_text", # Ключ для локализованной подсказки
        "state_name": "waiting_for_order_text",
        "next_field": "full_name",
        "input_type": "text"
    },
    {
        "key": "full_name",
        "prompt_key": "prompt_full_name", # Ключ для локализованной подсказки
        "state_name": "waiting_for_full_name",
        "next_field": "delivery_address",
        "input_type": "text"
    },
    {
        "key": "delivery_address",
        "prompt_key": "prompt_delivery_address", # Ключ для локализованной подсказки
        "state_name": "waiting_for_delivery_address",
        "next_field": "payment_method",
        "input_type": "text"
    },
    {
        "key": "payment_method",
        "prompt_key": "prompt_payment_method", # Ключ для локализованной подсказки
        "state_name": "waiting_for_payment_method",
        "next_field": "contact_phone",
        "input_type": "buttons",
        "options_keys": { # Теперь это словарь, где ключ - это ключ для локализации кнопки, значение - системное значение
            "button_payment_cash": "cash", # 'button_payment_cash' -> локализованный текст, 'cash' -> внутреннее значение
            "button_payment_card_on_delivery": "card_on_delivery"
        }
    },
    {
        "key": "contact_phone",
        "prompt_key": "prompt_contact_phone", # Ключ для локализованной подсказки
        "state_name": "waiting_for_contact_phone",
        "next_field": "delivery_notes",
        "input_type": "contact_button"
    },
    {
        "key": "delivery_notes",
        "prompt_key": "prompt_delivery_notes", # Ключ для локализованной подсказки
        "state_name": "waiting_for_delivery_notes",
        "next_field": "final_confirm",
        "input_type": "text"
    }
]

# Для быстрого доступа к конфигурации поля по его ключу
ORDER_FIELD_MAP = {field["key"]: field for field in ORDER_FIELDS_CONFIG}
