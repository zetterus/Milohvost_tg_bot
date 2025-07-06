import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Путь к директории с файлами локализаций
LOCALES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locales')

# Словарь для кэширования загруженных локализаций
_localized_strings: Dict[str, Dict[str, Any]] = {}


def _load_locale_file(lang_code: str) -> Optional[Dict[str, Any]]:
    """
    Загружает JSON-файл локализации для указанного языка.
    """
    file_path = os.path.join(LOCALES_DIR, f"{lang_code}.json")
    if not os.path.exists(file_path):
        logger.warning(f"Файл локализации для языка '{lang_code}' не найден: {file_path}")
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Файл локализации '{lang_code}.json' успешно загружен.")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON в файле '{lang_code}.json': {e}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при чтении файла '{lang_code}.json': {e}")
        return None


def get_localized_message(key: str, lang_code: str, default_lang_code: str = 'uk') -> str:
    """
    Получает локализованную строку по ключу для указанного языка.
    Если строка не найдена для заданного языка, пытается найти ее для языка по умолчанию.
    Если и там не найдена, возвращает сам ключ.
    """
    # Если локализация для языка еще не загружена, пытаемся ее загрузить
    if lang_code not in _localized_strings:
        loaded_data = _load_locale_file(lang_code)
        if loaded_data:
            _localized_strings[lang_code] = loaded_data
        else:
            # Если не удалось загрузить, используем язык по умолчанию
            logger.warning(f"Не удалось загрузить локализацию для '{lang_code}'. Используем '{default_lang_code}'.")
            lang_code = default_lang_code
            if lang_code not in _localized_strings:  # Повторная попытка для дефолта
                loaded_data_default = _load_locale_file(default_lang_code)
                if loaded_data_default:
                    _localized_strings[default_lang_code] = loaded_data_default
                else:
                    logger.critical(f"Не удалось загрузить локализацию для языка по умолчанию '{default_lang_code}'.")
                    return key  # Крайний случай: возвращаем сам ключ

    # Получаем строку для указанного языка
    message = _localized_strings.get(lang_code, {}).get(key)

    # Если строка не найдена для текущего языка, пробуем язык по умолчанию
    if message is None and lang_code != default_lang_code:
        logger.warning(
            f"Сообщение с ключом '{key}' не найдено для языка '{lang_code}'. Попытка найти для '{default_lang_code}'.")
        message = _localized_strings.get(default_lang_code, {}).get(key)

    # Если и в языке по умолчанию не найдено, возвращаем сам ключ (как заглушку)
    if message is None:
        logger.error(f"Сообщение с ключом '{key}' не найдено ни для языка '{lang_code}', ни для '{default_lang_code}'.")
        return key

    return str(message)  # Убедимся, что это строка


# # Дополнительная функция для загрузки всех локалей при старте (опционально)
# def load_all_locales_on_startup():
#     """
#     Загружает все доступные файлы локализаций при старте приложения.
#     Полезно, если вы хотите, чтобы все локали были доступны сразу.
#     """
#     for filename in os.listdir(LOCALES_DIR):
#         if filename.endswith(".json"):
#             lang_code = os.path.splitext(filename)[0]
#             if lang_code not in _localized_strings:
#                 loaded_data = _load_locale_file(lang_code)
#                 if loaded_data:
#                     _localized_strings[lang_code] = loaded_data
#     logger.info("Все доступные файлы локализаций загружены и кэшированы.")
