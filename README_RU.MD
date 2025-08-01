# Telegram Order Bot (русская версия)

Telegram-бот для простого и удобного приёма и управления заказами.  
Поддерживает три языка (🇺🇦 🇬🇧 🇷🇺), отслеживание статусов и админ-панель.

---

## 🔥 Возможности

- **Пошаговое оформление заказа** — простой wizard для клиентов  
- **История заказов** — пагинация по активным и завершённым  
- **Мультиязычность** — украинский, английский, русский (переключение «на лету»)  
- **Управление уведомлениями** — включить/отключить оповещения  
- **Инструменты администратора**  
  - просмотр всех заказов  
  - поиск и фильтры  
  - управление справочными сообщениями  
- **База данных** — SQLite + SQLAlchemy ORM (легко заменить на PostgreSQL/MySQL)  
- **Миграции** — Alembic

---

## 📂 Структура проекта

```
Milohvost_tg_bot/
├── .env                      # Переменные окружения (токен, ID админов и т.д.)
├── README.MD                 # Английская версия
├── README_RU.MD              # Русская версия (этот файл)
├── README_UA.MD              # Украинская версия
├── alembic/                  # Скрипты миграций Alembic
│   └── versions/
├── config.py                 # Константы и настройки
├── db.py                     # CRUD-операции
├── handlers/
│   ├── admin/                # Обработчики для админов
│   └── user/                 # Обработчики для пользователей
├── locales/
│   ├── uk.json               # Украинский
│   ├── en.json               # Английский
│   └── ru.json               # Русский
├── localization.py           # Утилиты локализации
├── main.py                   # Точка входа
├── models.py                 # SQLAlchemy-модели
├── requirements.txt          # Зависимости
└── show_structure.py         # Вывод дерева проекта
```

---

## ⚙️ Установка

### Требования
- Python 3.9+  
- Токен Telegram-бота от [@BotFather](https://t.me/BotFather)

### 1. Клонирование
```bash
git clone https://github.com/your-repo/telegram-order-bot.git
cd telegram-order-bot
```

### 2. Виртуальное окружение
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Зависимости
```bash
pip install -r requirements.txt
```

### 4. Переменные окружения
Создайте `.env` в корне:
```ini
BOT_TOKEN=ТОКЕН_ВАШЕГО_БОТА
ADMIN_IDS=123456789,987654321
DATABASE_NAME="ИМЯ_ВАШЕЙ_БД.db"
LOGGING_LEVEL=INFO
ORDERS_PER_PAGE="5"
MAX_PREVIEW_TEXT_LENGTH="20"
USER_ORDERS_PER_PAGE=5
```

### 5. Инициализация БД
```bash
alembic upgrade head
```

### 6. Запуск
```bash
python main.py
```

---

## 👤 Для пользователей

- `/start` — начало работы  
- Основное меню:
  - 📝 **Сделать заказ**  
  - 📋 **Мои заказы**  
  - ❓ **Помощь**  
  - 🌐 **Сменить язык**  
  - 🔔 **Уведомления** (вкл/выкл)

---

## 🛠️ Для админов

- `/admin` — открыть админ-меню  
- Доступные действия:
  - 📋 **Все заказы**  
  - 🔍 **Поиск заказов**  
  - 💬 **Управление справкой**  
- Админы получают уведомления о новых заказах

---

## 🌐 Локализация

1. Создайте `locales/xx.json` (где `xx` — код языка)  
2. Переведите все ключи из базового `en.json`  
3. Перезапустите бота

---

## 🗃️ Схема БД

| Таблица         | Назначение                              |
|-----------------|------------------------------------------|
| `users`         | пользователи, язык, настройки уведомлений |
| `orders`        | заказы, статус, детали                   |
| `help_messages` | локализованные тексты помощи             |

---

## 🔧 Технологии

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Aiogram 3.x](https://img.shields.io/badge/Aiogram-3.x-green.svg)](https://docs.aiogram.dev/)
[![SQLAlchemy ORM](https://img.shields.io/badge/SQLAlchemy-ORM-lightgrey.svg)](https://www.sqlalchemy.org/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-brightgreen.svg)](https://sqlite.org)
[![Alembic](https://img.shields.io/badge/Alembic-Migrations-blueviolet.svg)](https://alembic.sqlalchemy.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📄 Лицензия

Проект распространяется под [лицензией MIT](LICENSE).  
Вы можете:

- **использовать** его в любых целях (включая коммерческие),  
- **копировать**, **изменять**, **объединять**, **публиковать**, **распространять**, **передавать сублицензии** и **продавать** копии,  
- включать его в состав своих продуктов.

Единственное условие — сохранить исходное уведомление об авторстве и файл лицензии.
