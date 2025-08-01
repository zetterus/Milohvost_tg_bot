# Telegram Order Bot (українська версія)

Легкий Telegram-бот, який дозволяє клієнтам оформлювати замовлення за кілька кліків, а адміністраторам — повністю контролювати їх виконання.  
Підтримує три мови (🇺🇦 🇬🇧 🇷🇺), відстеження статусів у реальному часі та адмін-панель.

---

## 🔥 Можливості

- **Покроковий майстер замовлення** — максимально просто для клієнтів  
- **Історія замовлень** — пагінація активних і завершених  
- **Багатомовність** — українська, англійська, російська (перемикаються миттєво)  
- **Керування сповіщеннями** — увімкнути / вимкнути  
- **Інструменти адміна**
  - перегляд усіх замовлень  
  - пошук і фільтри  
  - керування довідковими повідомленнями  
- **База даних** — SQLite + SQLAlchemy ORM (заміна на PostgreSQL/MySQL — одна строка)  
- **Міграції** — Alembic

---

## 📂 Структура проєкту

```
Milohvost_tg_bot/
├── .env                      # Змінні середовища (токен, ID адмінів тощо)
├── README.MD                 # Англійський версія
├── README_RU.MD              # Російська версія
├── README_UA.MD              # Українська версія (українська)
├── alembic/                  # Скрипти міграцій Alembic
│   └── versions/
├── config.py                 # Константи та налаштування
├── db.py                     # CRUD-операції
├── handlers/
│   ├── admin/                # Обробники для адмінів
│   └── user/                 # Обробники для користувачів
├── locales/
│   ├── uk.json               # Українська
│   ├── en.json               # Англійська
│   └── ru.json               # Російська
├── localization.py           # Утиліти локалізації
├── main.py                   # Точка входу
├── models.py                 # Моделі SQLAlchemy
├── requirements.txt          # Залежності Python
└── show_structure.py         # Виведення дерева проєкту
```

---

## ⚙️ Встановлення

### Вимоги
- Python 3.9+  
- Токен Telegram-бота від [@BotFather](https://t.me/BotFather)

### 1. Клонування
```bash
git clone https://github.com/your-repo/telegram-order-bot.git
cd telegram-order-bot
```

### 2. Віртуальне середовище
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Встановлення залежностей
```bash
pip install -r requirements.txt
```

### 4. Змінні середовища
Створіть `.env` у корені проєкту:
```ini
BOT_TOKEN=ТОКЕН_ВАШОГО_БОТА
ADMIN_IDS=123456789,987654321
DATABASE_NAME="ІМ`Я_ВАШОЇ_БД.db"
LOGGING_LEVEL=INFO
ORDERS_PER_PAGE="5"
MAX_PREVIEW_TEXT_LENGTH="20"
USER_ORDERS_PER_PAGE=5
```

### 5. Ініціалізація БД
```bash
alembic upgrade head
```

### 6. Запуск
```bash
python main.py
```

---

## 👤 Для користувачів

- `/start` — початок роботи  
- Головне меню:
  - 📝 **Зробити замовлення**  
  - 📋 **Мої замовлення**  
  - ❓ **Допомога**  
  - 🌐 **Змінити мову**  
  - 🔔 **Сповіщення** (увімкнути / вимкнути)

---

## 🛠️ Для адмінів

- `/admin` — відкрити адмін-меню  
- Доступні дії:
  - 📋 **Усі замовлення**  
  - 🔍 **Пошук замовлень**  
  - 💬 **Керування довідкою**  
- Адміни отримують сповіщення про нові замовлення

---

## 🌐 Локалізація

1. Додайте `locales/xx.json` (`xx` = код мови)  
2. Перекладіть усі ключі з базового `en.json`  
3. Перезапустіть бота

---

## 🗃️ Схема БД

| Таблиця         | Призначення                                  |
|-----------------|----------------------------------------------|
| `users`         | інформація про користувачів, мова, сповіщення |
| `orders`        | деталі замовлень, статус                     |
| `help_messages` | локалізовані тексти довідки                  |

---

## 🔧 Технології

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Aiogram 3.x](https://img.shields.io/badge/Aiogram-3.x-green.svg)](https://docs.aiogram.dev/)
[![SQLAlchemy ORM](https://img.shields.io/badge/SQLAlchemy-ORM-lightgrey.svg)](https://www.sqlalchemy.org/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-brightgreen.svg)](https://sqlite.org)
[![Alembic](https://img.shields.io/badge/Alembic-Migrations-blueviolet.svg)](https://alembic.sqlalchemy.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📄 Ліцензія

Проєкт поширюється за [ліцензією MIT](LICENSE).  
Ви можете:

- **використовувати** його в будь-яких цілях (включаючи комерційні),  
- **копіювати**, **змінювати**, **об’єднувати**, **публікувати**, **поширювати**, **передавати субліцензії** та **продавати** копії,  
- включати його до складу своїх продуктів.

Єдина вимога — залишати оригінальне повідомлення про авторство та файл ліцензії.
