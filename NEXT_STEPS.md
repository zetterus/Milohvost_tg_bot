# Next Steps for Full Refactor Completion

## Current Status: ✅ Foundation Complete (Phases 1-3)

You now have a clean, reusable architecture. The next 4 phases will integrate it with your bot and add web functionality.


## Phase 4: Bot Handler Refactoring (Recommended Next)

**Goal**: Update bot handlers to use the new service layer

### Step 1: Create bot/ directory structure

```
bot/
├── __init__.py
├── main.py                    # Bot setup and entry point
├── middlewares/
│   └── localization_middleware.py  # (move from handlers/middlewares/)
├── states/
│   ├── __init__.py
│   ├── order_states.py        # (move from handlers/user/user_states.py)
│   └── admin_states.py        # (move from handlers/admin/admin_states.py)
├── keyboards/
│   ├── __init__.py
│   ├── user_keyboards.py      # Extract all keyboard builders
│   └── admin_keyboards.py
└── handlers/
    ├── __init__.py
    ├── user/
    │   ├── __init__.py
    │   ├── start.py           # /start handler
    │   ├── main_menu.py       # Main menu display
    │   ├── order_creation.py  # Order FSM (slimmed down)
    │   ├── order_viewing.py
    │   ├── settings.py        # Language + notifications
    │   └── help.py
    └── admin/
        ├── __init__.py
        ├── main_menu.py
        ├── orders.py          # Order management handlers
        ├── search.py
        ├── export.py
        └── help_messages.py
```

### Step 2: Extract Keyboards

Create `bot/keyboards/user_keyboards.py`:

```python
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def main_menu_keyboard(language: str) -> InlineKeyboardMarkup:
    """Main menu buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=get_localized_text("btn_new_order", language),
                callback_data="new_order"
            )],
            [InlineKeyboardButton(
                text=get_localized_text("btn_my_orders", language),
                callback_data="my_orders"
            )],
        ]
    )

def language_keyboard() -> InlineKeyboardMarkup:
    """Language selection."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🇺🇦 Українська", callback_data="lang_uk")],
            [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
            [InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en")],
        ]
    )
```

### Step 3: Refactor order_creation.py

Current file is 517 lines and mixes FSM, validation, UI, and DB calls.

**New version (~100 lines):**

```python
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from core import get_db_session
from repositories import OrderRepository, UserRepository
from services import OrderService, OrderCreateData, InvalidPhoneError, OrderValidationError
from bot.states import OrderStates
from localization import get_localized_text

router = Router()

@router.callback_query(F.data == "new_order_confirm")
async def confirm_order(callback_query, state: FSMContext):
    data = await state.get_data()
    lang = data.get("language", "uk")
    
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        user_repo = UserRepository(session)
        order_service = OrderService(order_repo, user_repo)
        
        try:
            order = await order_service.create_order(
                OrderCreateData(
                    user_id=callback_query.from_user.id,
                    username=callback_query.from_user.username or "web_form",
                    order_text=data["order_text"],
                    full_name=data.get("full_name"),
                    contact_phone=data.get("contact_phone"),
                    payment_method=data.get("payment_method")
                )
            )
            
            await callback_query.message.edit_text(
                get_localized_text("order_placed", lang).format(order_id=order.id)
            )
            
            # Notify admins
            for admin_id in settings.admin_ids:
                await bot.send_message(
                    admin_id,
                    f"New order #{order.id} from {order.username}"
                )
        
        except InvalidPhoneError:
            await callback_query.message.edit_text(
                get_localized_text("error_invalid_phone", lang)
            )
        except OrderValidationError as e:
            await callback_query.message.edit_text(
                get_localized_text("error_validation", lang)
            )
    
    await state.clear()
    await callback_query.answer()
```

**Benefits**:
- ✓ Business logic moved to OrderService
- ✓ Clear exception handling
- ✓ 5x fewer lines of code
- ✓ Reusable for web form
- ✓ Testable business logic


### Step 4: Update other handlers similarly

Convert remaining handlers in `handlers/user/` and `handlers/admin/` to use services.

**Time estimate**: 2-3 days


## Phase 5: Web Form with FastAPI

**Goal**: Create a web order form reusing OrderService

### Step 1: Create web_app structure

```
web_app/
├── __init__.py
├── app.py                 # FastAPI app factory
├── dependencies.py        # Dependency injection
├── schemas.py             # Pydantic models
├── routes/
│   ├── __init__.py
│   ├── health.py          # GET /healthz
│   └── orders.py          # POST /api/orders
└── templates/
    └── order_form.html

templates/
└── order_form.html        # HTML form
```

### Step 2: Create schemas

```python
# web_app/schemas.py
from pydantic import BaseModel, field_validator
from core import PHONE_NUMBER_REGEX, InvalidPhoneError

class WebOrderCreate(BaseModel):
    order_text: str
    full_name: str
    delivery_address: str
    contact_phone: str
    payment_method: str  # "cash" | "card_on_delivery"
    language: str = "uk"
    
    @field_validator("contact_phone")
    def validate_phone(cls, v):
        if not PHONE_NUMBER_REGEX.fullmatch(v):
            raise ValueError("Invalid phone number format")
        return v
```

### Step 3: Create FastAPI app

```python
# web_app/app.py
from fastapi import FastAPI, Depends
from core import engine, get_db_session, settings
from models import Base

app = FastAPI(title="Order Form")

@app.on_event("startup")
async def startup():
    # Create tables if needed
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.post("/api/orders")
async def create_order(order_data: WebOrderCreate, session = Depends(get_db_session)):
    order_repo = OrderRepository(session)
    user_repo = UserRepository(session)
    order_service = OrderService(order_repo, user_repo)
    
    order = await order_service.create_order(
        OrderCreateData(
            user_id=settings.web_form_user_id,
            username="web_form_user",
            order_text=order_data.order_text,
            full_name=order_data.full_name,
            contact_phone=order_data.contact_phone,
            payment_method=order_data.payment_method
        )
    )
    
    return {"order_id": order.id, "status": "created"}
```

**Time estimate**: 1-2 days


## Phase 6: Test Suite

**Goal**: Add comprehensive test coverage

### Unit Tests (services)

```python
# tests/test_order_service.py
import pytest
from services import OrderService, OrderCreateData, InvalidPhoneError

@pytest.mark.asyncio
async def test_create_order_valid(test_db):
    """Test creating a valid order."""
    order_repo = OrderRepository(test_db)
    user_repo = UserRepository(test_db)
    service = OrderService(order_repo, user_repo)
    
    order = await service.create_order(OrderCreateData(
        user_id=1,
        username="test",
        order_text="test order",
        contact_phone="+380991234567"
    ))
    
    assert order.id is not None
    assert order.status == "new"

@pytest.mark.asyncio
async def test_create_order_invalid_phone(test_db):
    """Test creating order with invalid phone."""
    order_repo = OrderRepository(test_db)
    user_repo = UserRepository(test_db)
    service = OrderService(order_repo, user_repo)
    
    with pytest.raises(InvalidPhoneError):
        await service.create_order(OrderCreateData(
            user_id=1,
            username="test",
            order_text="test",
            contact_phone="invalid"
        ))
```

### Integration Tests (repositories)

```python
# tests/test_repositories.py
@pytest.mark.asyncio
async def test_order_search(test_db):
    """Test order search."""
    order_repo = OrderRepository(test_db)
    
    await order_repo.create(
        user_id=1, username="john",
        order_text="I need a laptop"
    )
    
    results, count = await order_repo.search("laptop")
    assert count == 1
    assert results[0].order_text == "I need a laptop"
```

### End-to-End Tests (web routes)

```python
# tests/test_web_routes.py
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_order_api(web_client):
    """Test web form API."""
    response = await web_client.post(
        "/api/orders",
        json={
            "order_text": "test",
            "full_name": "John Doe",
            "contact_phone": "+380991234567"
        }
    )
    
    assert response.status_code == 200
    assert "order_id" in response.json()
```

**Time estimate**: 1-2 days


## Phase 7: Entrypoints

**Goal**: Clean entry points for running bot and web

### main_bot.py

```python
import asyncio
import logging
from aiogram import Bot, Dispatcher
from core import settings
from bot.main import setup_bot

logging.basicConfig(level=settings.logging_level)

async def main():
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    
    await setup_bot(dp)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
```

Run with:
```bash
python main_bot.py
```

### main_web.py

```python
from web_app.app import app

# Run with: uvicorn main_web:app --reload
```

**Time estimate**: 0.5 day


## Complete Timeline

- **Phase 4** (Bot refactoring): 2-3 days
- **Phase 5** (Web form): 1-2 days  
- **Phase 6** (Tests): 1-2 days
- **Phase 7** (Entrypoints): 0.5 day

**Total**: ~5-7 days to complete full refactor


## Recommended Path Forward

### Option A: Quick Web Form (Best for immediate MVP)
1. ✅ Phase 1-3: DONE
2. ⏭️ Phase 5: Create web form using existing services (1-2 days)
3. Keep old bot handlers working as-is
4. Later: Phase 4 (refactor bot handlers gradually)

### Option B: Full Clean Refactor (Best for long-term)
1. ✅ Phase 1-3: DONE
2. ⏭️ Phase 4: Refactor bot handlers (2-3 days)
3. ⏭️ Phase 5: Add web form (1 day)
4. ⏭️ Phase 6: Add tests (1-2 days)
5. ⏭️ Phase 7: Clean entrypoints (0.5 day)

### Option C: Incremental (Balance both)
1. ✅ Phase 1-3: DONE
2. ⏭️ Phase 5: Quick web form MVP (1 day, reuse services)
3. ⏭️ Phase 4: Gradually migrate bot handlers (do in parallel with Phase 5 & 6)
4. ⏭️ Phase 6: Add tests (prioritize critical paths)


## Questions to Guide Your Decision

1. **Need web form urgently?** → Option A (quickest path)
2. **Want clean, maintainable code long-term?** → Option B (most thorough)
3. **Need balance of speed and quality?** → Option C (recommended)

All options build on the solid Phase 1-3 foundation you now have.


## Key Files to Remember

- **`REFACTOR_STATUS.md`** - Current status of all phases
- **`USAGE_EXAMPLES.md`** - How to use each layer
- **`core/config.py`** - All settings and constants
- **`services/`** - The heart of your business logic
- **`repositories/`** - How to query the database
- **`models.py`** - Your database schema

Good luck! 🚀

