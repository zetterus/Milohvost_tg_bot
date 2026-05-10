# Full Refactor Plan — Best Practices

## Summary of issues found in current codebase

| File | Lines | Problem |
|---|---|---|
| `db.py` | 537 | God module — users, orders, help_messages all in one file, no separation |
| `handlers/user/order_creation.py` | 517 | Mixes FSM control, input validation, DB calls, and string formatting |
| `handlers/user/user_utils.py` | 325 | Mixes utility functions with live route handlers on the same file |
| `config.py` | 138 | Uses raw `os.getenv()` — no startup validation, silent None on missing BOT_TOKEN |
| `main.py` | 123 | Registers FSMContextMiddleware manually (aiogram 3 already handles this internally) |
| No service layer | — | Business logic is scattered across handlers and db.py |
| No repositories | — | DB queries are directly called from handlers |
| No tests | — | Zero test coverage |
| No `.env.example` | — | Env vars undocumented for new devs |
| No custom exceptions | — | Error handling is ad-hoc per handler |

---

## Target Architecture

Layered architecture with strict direction of dependencies:

```
handlers/routes → services → repositories → models
```

No layer talks to a layer above it. Services don't import aiogram types. Repositories don't import service logic.

---

## Target File Structure

```
Milohvost_tg_bot/
│
├── .env                            # unchanged
├── .env.example                    # NEW: document every required/optional var
├── .gitignore                      # ensure .env excluded
├── alembic/                        # unchanged
├── alembic.ini                     # unchanged
├── models.py                       # unchanged (already clean)
├── requirements.txt                # UPDATED: add pydantic-settings, fastapi, uvicorn, jinja2, python-multipart, pytest, httpx
│
├── core/                           # NEW: shared infrastructure
│   ├── __init__.py
│   ├── config.py                   # pydantic-settings Settings class (replaces config.py)
│   ├── database.py                 # engine + AsyncSessionLocal + get_db_session (extracted from db.py)
│   └── exceptions.py              # NEW: OrderNotFound, UserNotFound, ValidationError etc.
│
├── repositories/                   # NEW: data access layer (extracted from db.py)
│   ├── __init__.py
│   ├── base.py                     # AbstractRepository with common CRUD signature
│   ├── orders.py                   # OrderRepository: create, get_by_id, get_all_paginated, search, delete, update
│   ├── users.py                    # UserRepository: get_or_create, update_language, update_notifications
│   └── help_messages.py            # HelpMessageRepository: all help message CRUD
│
├── services/                       # NEW: business logic layer
│   ├── __init__.py
│   ├── order_service.py            # create_order(), validate_order_data() — shared by bot and web
│   ├── user_service.py             # get_or_create_user(), change_language(), toggle_notifications()
│   ├── notification_service.py     # send_admin_notification(), send_user_notification() (from user_utils.py)
│   └── help_message_service.py    # activate, deactivate, create, delete help messages
│
├── bot/                            # bot-specific code (replaces handlers/)
│   ├── __init__.py
│   ├── main.py                     # bot setup: Bot, Dispatcher, middlewares, routers
│   ├── middlewares/
│   │   └── localization_middleware.py  # MOVED unchanged
│   ├── states/
│   │   ├── __init__.py
│   │   ├── order_states.py         # MOVED from handlers/user/user_states.py
│   │   └── admin_states.py         # MOVED from handlers/admin/admin_states.py
│   ├── keyboards/                  # NEW: extract all InlineKeyboardBuilder logic from handlers
│   │   ├── __init__.py
│   │   ├── user_keyboards.py       # main_menu_kb(), order_confirm_kb(), language_kb(), notification_kb()
│   │   └── admin_keyboards.py      # admin_menu_kb(), order_list_kb(), order_detail_kb(), pagination_kb()
│   └── handlers/
│       ├── __init__.py             # exports user_router, admin_router
│       ├── user/
│       │   ├── __init__.py
│       │   ├── start.py            # /start handler only
│       │   ├── main_menu.py        # main menu display + back callback
│       │   ├── order_creation.py   # SLIMMED: FSM flow only, calls order_service
│       │   ├── order_viewing.py    # MOVED unchanged
│       │   ├── settings.py         # language + notification handlers (from user_utils.py)
│       │   └── help.py             # MOVED unchanged
│       └── admin/
│           ├── __init__.py
│           ├── main_menu.py        # /admin + admin menu handlers
│           ├── orders.py           # order list, details, status change, edit text
│           ├── search.py           # search flow handlers
│           ├── export.py           # CSV export handlers
│           └── help_messages.py    # help message management handlers
│
├── web_app/                        # NEW: FastAPI web order form
│   ├── __init__.py
│   ├── app.py                      # FastAPI app factory with lifespan
│   ├── dependencies.py             # get_order_service(), get_db()
│   ├── schemas.py                  # WebOrderCreate Pydantic model (phone validated with PHONE_NUMBER_REGEX)
│   └── routes/
│       ├── __init__.py
│       ├── health.py               # GET /healthz
│       └── orders.py               # GET /order-form, POST /order-form, POST /api/orders
│
├── templates/                      # NEW: Jinja2 HTML templates
│   └── order_form.html
│
├── static/                         # NEW: CSS/JS assets
│   └── styles.css
│
├── tests/                          # NEW: test suite
│   ├── __init__.py
│   ├── conftest.py                 # shared fixtures: test DB, test client, mock services
│   ├── test_order_service.py       # unit tests for order_service
│   ├── test_repositories.py        # integration tests with in-memory SQLite
│   └── test_web_routes.py          # httpx AsyncClient tests for /healthz, /api/orders
│
├── scripts/
│   └── smoke_web_form.py           # quick end-to-end smoke test (httpx)
│
├── main_bot.py                     # NEW entrypoint: `python main_bot.py` runs the bot
├── main_web.py                     # NEW entrypoint: `uvicorn main_web:app` runs the web server
└── locales/
    ├── en.json                     # unchanged
    ├── ru.json                     # unchanged
    └── uk.json                     # unchanged
```

---

## Phase-by-phase implementation

### Phase 1 — Core infrastructure (no behavior change)

1. **`core/config.py`** — Replace `os.getenv` with `pydantic-settings`:

   ```python
   from pydantic_settings import BaseSettings, SettingsConfigDict
   from pydantic import field_validator
   import re

   class Settings(BaseSettings):
       bot_token: str
       admin_ids: list[int] = []
       database_name: str = "orders_bot.db"
       logging_level: str = "INFO"
       orders_per_page: int = 10
       max_preview_text_length: int = 30
       user_orders_per_page: int = 5
       web_form_user_id: int = -1       # synthetic user_id for web orders
       web_host: str = "127.0.0.1"
       web_port: int = 8080

       model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

   settings = Settings()   # raises ValidationError at startup if bot_token missing
   ```

   - **benefit**: `BOT_TOKEN` missing = crash with clear message instantly (not silent None)
   - All `ORDER_FIELDS_CONFIG`, `ORDER_FIELD_MAP`, `PHONE_NUMBER_REGEX` stay in `core/config.py` unchanged

2. **`core/database.py`** — Only engine + session, no business logic:

   ```python
   engine = create_async_engine(f"sqlite+aiosqlite:///{settings.database_name}", ...)
   AsyncSessionLocal = sessionmaker(...)

   @asynccontextmanager
   async def get_db_session() -> AsyncGenerator[AsyncSession, None]: ...
   ```

3. **`core/exceptions.py`** — Custom domain exceptions:

   ```python
   class OrderNotFoundError(Exception): ...
   class UserNotFoundError(Exception): ...
   class InvalidPhoneError(ValueError): ...
   class OrderValidationError(ValueError): ...
   ```

4. **`.env.example`**:
   ```ini
   BOT_TOKEN=your_telegram_bot_token_here
   ADMIN_IDS=123456789,987654321
   DATABASE_NAME=milohvost.db
   ORDERS_PER_PAGE=10
   MAX_PREVIEW_TEXT_LENGTH=30
   USER_ORDERS_PER_PAGE=5
   WEB_HOST=127.0.0.1
   WEB_PORT=8080
   ```

---

### Phase 2 — Repository layer (extracted from `db.py`)

Each repository takes an `AsyncSession` injected via constructor.

**`repositories/orders.py`**:
```python
class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id, username, order_text, **kwargs) -> Order: ...
    async def get_by_id(self, order_id: int) -> Order | None: ...
    async def get_all_paginated(self, offset: int, limit: int) -> tuple[list[Order], int]: ...
    async def search(self, query: str, offset: int, limit: int) -> tuple[list[Order], int]: ...
    async def update_status(self, order_id: int, status: str) -> bool: ...
    async def update_text(self, order_id: int, text: str) -> bool: ...
    async def delete(self, order_id: int) -> bool: ...
```

**`repositories/users.py`**:
```python
class UserRepository:
    async def get_or_create(self, user_id, username, first_name, last_name) -> User: ...
    async def get_language(self, user_id: int) -> str: ...
    async def update_language(self, user_id: int, lang: str) -> User | None: ...
    async def get_notifications_status(self, user_id: int) -> bool | None: ...
    async def update_notifications(self, user_id: int, enabled: bool) -> User | None: ...
```

**`repositories/help_messages.py`**:
```python
class HelpMessageRepository:
    async def create(self, text, lang, is_active) -> HelpMessage: ...
    async def get_active(self, lang: str) -> HelpMessage | None: ...
    async def set_active(self, message_id, lang) -> HelpMessage | None: ...
    async def deactivate(self, message_id) -> bool: ...
    async def delete(self, message_id) -> bool: ...
    async def get_all(self, lang=None) -> list[HelpMessage]: ...
```

---

### Phase 3 — Service layer

Services contain the business logic. They:
- Accept repository instances (not sessions directly)
- Raise domain exceptions from `core/exceptions.py`
- Know nothing about aiogram types or HTTP request/response types

**`services/order_service.py`**:
```python
class OrderService:
    def __init__(self, order_repo: OrderRepository, user_repo: UserRepository) -> None: ...

    async def create_order(self, data: OrderCreateData) -> Order:
        """Validates input, creates order. Raises OrderValidationError on bad data."""
        if not PHONE_NUMBER_REGEX.fullmatch(data.contact_phone):
            raise InvalidPhoneError(data.contact_phone)
        return await self._order_repo.create(**asdict(data))

    async def get_order_or_raise(self, order_id: int) -> Order:
        order = await self._order_repo.get_by_id(order_id)
        if not order:
            raise OrderNotFoundError(order_id)
        return order
```

**`services/notification_service.py`**:
```python
class NotificationService:
    def __init__(self, bot: Bot, user_repo: UserRepository, order_repo: OrderRepository) -> None: ...
    async def notify_admins_new_order(self, order_id: int, admin_ids: list[int]) -> None: ...
    async def notify_user_order_placed(self, user_id: int, order_id: int, lang: str) -> None: ...
```

---

### Phase 4 — Slim bot handlers

After services exist, handlers become thin:

```python
@router.callback_query(F.data == "final_confirm_order")
async def final_confirm_order(
    callback: CallbackQuery,
    state: FSMContext,
    order_service: OrderService,        # injected via middleware/DI
    notification_service: NotificationService,
    lang: str
):
    user_data = await state.get_data()
    try:
        order = await order_service.create_order(OrderCreateData(
            user_id=callback.from_user.id,
            username=callback.from_user.username or "web_form",
            **user_data
        ))
    except OrderValidationError as e:
        await callback.message.edit_text(get_localized_message("error_order_processing", lang))
        return

    await callback.message.edit_text(
        get_localized_message("order_placed_success", lang).format(order_id=order.id)
    )
    await notification_service.notify_admins_new_order(order.id, settings.admin_ids)
    await state.clear()
    await callback.answer()
```

**`bot/keyboards/user_keyboards.py`** — extract all `InlineKeyboardBuilder` blocks:
```python
def main_menu_kb(lang: str) -> InlineKeyboardMarkup: ...
def order_confirm_kb(lang: str, field_key: str) -> InlineKeyboardMarkup: ...
def language_kb(lang: str) -> InlineKeyboardMarkup: ...
def notification_settings_kb(lang: str, is_enabled: bool) -> InlineKeyboardMarkup: ...
```

---

### Phase 5 — Web form (FastAPI)

**`web_app/app.py`**:
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: verify DB accessible
    yield
    # shutdown: close engine

app = FastAPI(lifespan=lifespan, title="Order Web Form")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(health_router)
app.include_router(orders_router)
```

**`web_app/schemas.py`**:
```python
from pydantic import BaseModel, field_validator
from typing import Literal
from core.config import settings, PHONE_NUMBER_REGEX

class WebOrderCreate(BaseModel):
    order_text: str
    full_name: str
    delivery_address: str
    payment_method: Literal["cash", "card_on_delivery"]
    contact_phone: str
    delivery_notes: str | None = None
    lang: str = "uk"

    @field_validator("contact_phone")
    @classmethod
    def validate_phone(cls, v):
        if not PHONE_NUMBER_REGEX.fullmatch(v):
            raise ValueError("Invalid phone number format")
        return v
```

**`web_app/routes/orders.py`** — 3 routes:
- `GET /order-form?lang=uk` → render `order_form.html` with localized labels
- `POST /order-form` → accept form fields, redirect with success/error
- `POST /api/orders` → JSON in, `{"order_id": ..., "status": "new"}` out

---

### Phase 6 — Tests

**`tests/conftest.py`**:
```python
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from httpx import AsyncClient, ASGITransport
from web_app.app import app

@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    # create tables, yield session, drop after

@pytest_asyncio.fixture
async def web_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
```

**`tests/test_order_service.py`**:
```python
async def test_create_order_success(test_db): ...
async def test_create_order_invalid_phone_raises(test_db): ...
async def test_get_order_not_found_raises(test_db): ...
```

**`tests/test_web_routes.py`**:
```python
async def test_healthz_ok(web_client): ...
async def test_api_create_order_valid(web_client): ...
async def test_api_create_order_bad_phone(web_client): ...
```

---

### Phase 7 — Entrypoints

**`main_bot.py`**:
```python
import asyncio
from bot.main import run_bot

if __name__ == "__main__":
    asyncio.run(run_bot())
```

**`main_web.py`**:
```python
from web_app.app import app  # uvicorn entry: uvicorn main_web:app --reload
```

---

## New dependencies to add

```
pydantic-settings==2.3.4   # replaces raw os.getenv
fastapi==0.115.0
uvicorn==0.30.0
jinja2==3.1.4
python-multipart==0.0.9
pytest==8.2.0
pytest-asyncio==0.23.7
httpx==0.27.0
```

---

## Comparison with current plan (incremental web-first)

| Aspect | Current plan (web-first) | Full refactor |
|---|---|---|
| Time to ship web form | ~1 day | ~5–7 days |
| Shared logic | Copy-paste or import from handlers | Clean service layer shared by bot + web |
| Test coverage | Smoke test only | Unit + integration + e2e |
| Handler size | Still 500+ line files | Thin handlers (~20–50 lines each) |
| Adding features later | Increasing duplication | Add service method, plug into any entry point |
| Risk of breaking bot | Low | Medium (mitigated by tests in phase 6) |
| Recommended order | Acceptable for MVP | Do this if longevity matters |

---

## Recommended decision

- **Choose full refactor** if you plan to maintain and extend this beyond 3 months.
- **Choose incremental web-first** if you need the form live within 1–2 days.
- **Best of both**: Do Phase 1–3 (core + repositories + services) first — that's ~2 days — then implement the web form using clean services from day one. Skip keyboard extraction and test suite for now; add Phase 4, 6 post-launch.

