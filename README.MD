# Telegram Order Bot (English)

A lightweight Telegram bot that lets customers place orders in a few taps and gives admins full visibility and control over their fulfilment.  
Supports three languages (🇺🇦 🇬🇧 🇷🇺), real-time status tracking and an admin panel.

---

## 🔥 Features

- **Step-by-step order wizard** — effortless for customers  
- **Order history** — paginated active and past orders  
- **Multilingual** — Ukrainian, English, Russian (switch on-the-fly)  
- **Notification toggle** — enable / disable alerts  
- **Admin tools**
  - browse all orders  
  - search & filters  
  - manage help messages  
- **Database** — SQLite + SQLAlchemy ORM (swap to PostgreSQL/MySQL in one line)  
- **Migrations** — Alembic

---

## 📂 Project Tree

```
Milohvost_tg_bot/
├── .env                      # Environment variables (token, admin IDs, etc.)
├── README.MD                 # English description (this file)
├── README_RU.MD              # Russian description
├── README_UA.MD              # Ukrainian description
├── alembic/                  # Alembic migration scripts
│   └── versions/
├── config.py                 # Constants and settings
├── db.py                     # CRUD helpers
├── handlers/
│   ├── admin/                # Admin-only handlers
│   └── user/                 # Customer handlers
├── locales/
│   ├── uk.json               # Ukrainian
│   ├── en.json               # English
│   └── ru.json               # Russian
├── localization.py           # i18n utilities
├── main.py                   # Bot entry point
├── models.py                 # SQLAlchemy models
├── requirements.txt          # Python dependencies
└── show_structure.py         # CLI tree printer
```

---

## ⚙️ Setup

### Prerequisites
- Python 3.9+  
- Telegram bot token from [@BotFather](https://t.me/BotFather)

### 1. Clone
```bash
git clone https://github.com/your-repo/telegram-order-bot.git
cd telegram-order-bot
```

### 2. Virtual environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 3. Install deps
```bash
pip install -r requirements.txt
```

### 4. Environment variables
Create `.env` in the project root:
```ini
BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_IDS=123456789,987654321
DATABASE_NAME="YOUR_DB_NAME.db"
LOGGING_LEVEL=INFO
ORDERS_PER_PAGE="5"
MAX_PREVIEW_TEXT_LENGTH="20"
USER_ORDERS_PER_PAGE=5

```

### 5. Database
```bash
alembic upgrade head
```

### 6. Run
```bash
python main.py
```

---

## 👤 For Customers

- `/start` — begin interaction  
- Main menu:
  - 📝 **Make an Order**  
  - 📋 **My Orders**  
  - ❓ **Get Help**  
  - 🌐 **Change Language**  
  - 🔔 **Notification Settings**

---

## 🛠️ For Admins

- `/admin` — open admin menu  
- Available actions:
  - 📋 **All Orders**  
  - 🔍 **Search Orders**  
  - 💬 **Manage Help Messages**  
- Admins receive new-order notifications

---

## 🌐 Localization

1. Add `locales/xx.json` (`xx` = language code)  
2. Translate all keys from base `en.json`  
3. Restart the bot

---

## 🗃️ Database Schema

| Table           | Purpose                                   |
|-----------------|-------------------------------------------|
| `users`         | user info, language, notification prefs   |
| `orders`        | order details, status                     |
| `help_messages` | localized help texts                      |

---

## 🔧 Tech Stack

[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![Aiogram 3.x](https://img.shields.io/badge/Aiogram-3.x-green.svg)](https://docs.aiogram.dev/)
[![SQLAlchemy ORM](https://img.shields.io/badge/SQLAlchemy-ORM-lightgrey.svg)](https://www.sqlalchemy.org/)
[![SQLite](https://img.shields.io/badge/SQLite-Database-brightgreen.svg)](https://sqlite.org)
[![Alembic](https://img.shields.io/badge/Alembic-Migrations-blueviolet.svg)](https://alembic.sqlalchemy.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📄 License

MIT — see [LICENSE](LICENSE).
