import csv
import io
from datetime import datetime
from typing import List, Dict, Any

from models import Order
from localization import get_localized_message, get_available_languages
from config import ORDER_FIELD_NAMES_KEYS, ORDER_FIELD_MAP

import logging

logger = logging.getLogger(__name__)

async def generate_orders_csv(orders: List[Order], lang: str) -> io.BytesIO:
    """
    Генерирует CSV-файл со списком заказов.

    :param orders: Список объектов Order для экспорта.
    :param lang: Код языка для локализации заголовков и значений.
    :return: Объект io.BytesIO, содержащий данные CSV.
    """
    logger.info(f"Начало генерации CSV для {len(orders)} заказов на языке '{lang}'.")

    output = io.StringIO()
    writer = csv.writer(output)

    # Определяем заголовки CSV
    # Используем ORDER_FIELD_NAMES_KEYS для получения локализованных названий полей
    # Дополнительные поля, которые не являются частью ORDER_FIELDS_CONFIG, но есть в модели Order
    header_keys = [
        "id", "user_id", "username", "order_text", "full_name",
        "delivery_address", "payment_method", "contact_phone",
        "delivery_notes", "status", "created_at", "sent_at", "received_at"
    ]

    # Локализуем заголовки
    localized_headers = []
    for key in header_keys:
        if key in ORDER_FIELD_NAMES_KEYS:
            localized_headers.append(get_localized_message(ORDER_FIELD_NAMES_KEYS[key], lang))
        elif key == "id": # ID заказа
            localized_headers.append(get_localized_message("order_details_order_id", lang).replace("№{order_id}", "").strip())
        elif key == "user_id": # ID пользователя
            localized_headers.append(get_localized_message("order_details_user", lang).split("(ID:")[0].strip())
        elif key == "username": # Юзернейм
            localized_headers.append(get_localized_message("field_name_username", lang)) # Добавим этот ключ в ru.json
        elif key == "status": # Статус
            localized_headers.append(get_localized_message("order_details_status_prefix", lang))
        elif key == "created_at": # Дата создания
            localized_headers.append(get_localized_message("order_details_created_at", lang).replace(":", "").strip())
        elif key == "sent_at": # Дата отправки (новое поле)
            localized_headers.append(get_localized_message("field_name_sent_at", lang)) # Добавим этот ключ
        elif key == "received_at": # Дата получения (новое поле)
            localized_headers.append(get_localized_message("field_name_received_at", lang)) # Добавим этот ключ
        else:
            localized_headers.append(key) # Fallback для неизвестных ключей

    writer.writerow(localized_headers)

    # Записываем данные заказов
    for order in orders:
        row = []
        for key in header_keys:
            value = getattr(order, key)

            # Специальная обработка для некоторых полей
            if key == "payment_method" and value:
                payment_options = ORDER_FIELD_MAP.get("payment_method", {}).get("options_keys", {})
                # Ищем ключ локализации для выбранного значения
                localized_payment_method_key = next((k for k, v in payment_options.items() if v == value), None)
                if localized_payment_method_key:
                    value = get_localized_message(localized_payment_method_key, lang)
            elif key == "delivery_notes" and (value is None or str(value).strip() == '-' or str(value).strip().lower() == get_localized_message("no_notes_keyword", lang).lower()):
                value = get_localized_message("no_notes_display", lang)
            elif key.endswith("_at") and isinstance(value, datetime):
                value = value.strftime('%d.%m.%Y %H:%M:%S') # Форматируем дату и время
            elif value is None:
                value = get_localized_message("not_specified", lang) # Для всех остальных None значений
            elif key == "status":
                value = get_localized_message(f"order_status_{value}", lang) # Локализуем статус

            row.append(str(value)) # Преобразуем все в строку

        writer.writerow(row)

    output.seek(0) # Перемещаем указатель в начало потока
    logger.info(f"CSV-файл успешно сгенерирован для {len(orders)} заказов.")
    return io.BytesIO(output.getvalue().encode('utf-8')) # Возвращаем BytesIO с UTF-8 кодировкой
