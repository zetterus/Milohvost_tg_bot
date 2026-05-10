# Quick Start Guide - Using the New Architecture

## How to Use the Core Layer

### Configuration

```python
from core import settings

# Access any setting
print(settings.bot_token)
print(settings.admin_ids)
print(settings.database_name)
print(settings.web_host)

# All values are validated at import time
# If BOT_TOKEN is missing, you'll get a clear ValidationError
```

### Database Sessions

```python
from core import get_db_session
from repositories import OrderRepository

async def my_function():
    # Use context manager for automatic commit/rollback
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        order = await order_repo.get_by_id(123)
```

### Exceptions

```python
from core import InvalidPhoneError, OrderValidationError

try:
    await order_service.create_order(data)
except InvalidPhoneError as e:
    print(f"Phone error: {e.phone_number}")
except OrderValidationError as e:
    print(f"Validation error for {e.field}: {e}")
```


## How to Use the Repository Layer

### Getting Data

```python
from core import get_db_session
from repositories import OrderRepository, UserRepository

async def example():
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        
        # Get single order
        order = await order_repo.get_by_id(1)
        
        # Get paginated list
        orders, total = await order_repo.get_all(offset=0, limit=10)
        
        # Search
        results, count = await order_repo.search("query text", offset=0, limit=10)
        
        # Get user's orders
        user_orders, user_total = await order_repo.get_user_orders(user_id=123)
```

### Creating Data

```python
async def create_example():
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        
        order = await order_repo.create(
            user_id=123,
            username="john_doe",
            order_text="I need a laptop",
            full_name="John Doe",
            delivery_address="123 Main St",
            payment_method="cash",
            contact_phone="+380991234567",
            delivery_notes="Leave at door"
        )
        
        return order.id
```

### Updating Data

```python
async def update_example():
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        
        # Update status
        success = await order_repo.update_status(order_id=1, new_status="shipped")
        
        # Update text
        success = await order_repo.update_text(order_id=1, new_text="Updated order text")
        
        # Generic update
        success = await order_repo.update(
            order_id=1,
            full_name="New Name",
            payment_method="card"
        )
```

### User Repository

```python
async def user_example():
    async with get_db_session() as session:
        user_repo = UserRepository(session)
        
        # Get or create
        user = await user_repo.get_or_create(
            user_id=123,
            username="john_doe",
            first_name="John",
            last_name="Doe"
        )
        
        # Change language
        user = await user_repo.update_language(user_id=123, language_code="en")
        
        # Update notifications
        user = await user_repo.update_notifications(user_id=123, enabled=False)
```


## How to Use the Service Layer

### Order Service

```python
from core import get_db_session
from repositories import OrderRepository, UserRepository
from services import OrderService, OrderCreateData

async def service_example():
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        user_repo = UserRepository(session)
        
        # Create service with injected repositories
        order_service = OrderService(order_repo, user_repo)
        
        # Create validated order
        order_data = OrderCreateData(
            user_id=123,
            username="john_doe",
            order_text="I need a laptop",
            contact_phone="+380991234567"
        )
        
        try:
            order = await order_service.create_order(order_data)
            print(f"Order {order.id} created!")
        except InvalidPhoneError as e:
            print(f"Invalid phone: {e.phone_number}")
        except OrderValidationError as e:
            print(f"Validation error: {e}")
```

### User Service

```python
from repositories import UserRepository
from services import UserService

async def user_service_example():
    async with get_db_session() as session:
        user_repo = UserRepository(session)
        user_service = UserService(user_repo)
        
        # Get or create user
        user = await user_service.get_or_create_user(
            user_id=123,
            username="john_doe"
        )
        
        # Get language
        language = await user_service.get_user_language(123)
        
        # Change language
        user = await user_service.change_user_language(123, "en")
        
        # Toggle notifications
        user = await user_service.toggle_notifications(123, enabled=True)
```

### Help Message Service

```python
from repositories import HelpMessageRepository
from services import HelpMessageService

async def help_service_example():
    async with get_db_session() as session:
        help_repo = HelpMessageRepository(session)
        help_service = HelpMessageService(help_repo)
        
        # Create help message
        msg = await help_service.create_help_message(
            message_text="Welcome to our shop!",
            language_code="uk",
            is_active=True  # Will auto-deactivate other active messages
        )
        
        # Get active message for language
        active_msg = await help_service.get_active_help_message("uk")
        
        # Activate different message
        msg = await help_service.set_active_help_message(msg_id=2, language_code="uk")
```


## Integration with Telegram Bot

### Example Aiogram Handler Using Services

```python
from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from core import get_db_session, settings
from repositories import OrderRepository, UserRepository
from services import OrderService, OrderCreateData, InvalidPhoneError, OrderValidationError

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    # Get user through service
    async with get_db_session() as session:
        user_repo = UserRepository(session)
        user_service = UserService(user_repo)
        
        user = await user_service.get_or_create_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )
    
    await message.answer(f"Hello, {user.first_name}!")
```

### Example: Create Order Handler

```python
@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    async with get_db_session() as session:
        order_repo = OrderRepository(session)
        user_repo = UserRepository(session)
        order_service = OrderService(order_repo, user_repo)
        
        try:
            order = await order_service.create_order(
                OrderCreateData(
                    user_id=callback.from_user.id,
                    username=callback.from_user.username or "unknown",
                    order_text=data["order_text"],
                    full_name=data["full_name"],
                    contact_phone=data["phone"],
                    payment_method=data["payment"]
                )
            )
            
            await callback.message.edit_text(
                f"✓ Order created! ID: {order.id}"
            )
            
        except InvalidPhoneError:
            await callback.message.edit_text("❌ Invalid phone number")
        except OrderValidationError as e:
            await callback.message.edit_text(f"❌ Error: {e}")
        
        await state.clear()
```


## Migrating from Old db.py to New Services

### Old Way
```python
from db import add_new_order, get_order_by_id, update_order_status

order = await add_new_order(user_id=123, username="john", order_text="hello")
order = await get_order_by_id(order.id)
await update_order_status(order.id, "shipped")
```

### New Way
```python
from core import get_db_session
from repositories import OrderRepository, UserRepository
from services import OrderService, OrderCreateData

async with get_db_session() as session:
    order_repo = OrderRepository(session)
    user_repo = UserRepository(session)
    order_service = OrderService(order_repo, user_repo)
    
    order = await order_service.create_order(
        OrderCreateData(user_id=123, username="john", order_text="hello")
    )
    order = await order_service.get_order(order.id)
    await order_service.update_order_status(order.id, "shipped")
```

**Benefits of new way**:
- ✓ Validated input (OrderCreateData)
- ✓ Phone validation built-in
- ✓ Clear exceptions (InvalidPhoneError, OrderValidationError)
- ✓ Reusable in bot handlers and web forms
- ✓ Testable without database


## Testing with New Architecture

```python
import pytest
from core import get_db_session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from models import Base

@pytest_asyncio.fixture
async def test_db():
    """Create in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    TestSessionLocal = sessionmaker(
        expire_on_commit=False,
        class_=AsyncSession,
        bind=engine
    )
    
    async with TestSessionLocal() as session:
        yield session
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_order(test_db):
    order_repo = OrderRepository(test_db)
    user_repo = UserRepository(test_db)
    order_service = OrderService(order_repo, user_repo)
    
    order = await order_service.create_order(
        OrderCreateData(
            user_id=1,
            username="test",
            order_text="test order",
            contact_phone="+380991234567"
        )
    )
    
    assert order.id is not None
    assert order.order_text == "test order"

@pytest.mark.asyncio
async def test_invalid_phone(test_db):
    order_repo = OrderRepository(test_db)
    user_repo = UserRepository(test_db)
    order_service = OrderService(order_repo, user_repo)
    
    with pytest.raises(InvalidPhoneError):
        await order_service.create_order(
            OrderCreateData(
                user_id=1,
                username="test",
                order_text="test",
                contact_phone="invalid"
            )
        )
```


## Summary

The new architecture allows you to:

1. **Create business logic once** (in services)
2. **Use it everywhere** (bot handlers, web forms, tests, APIs)
3. **Test independently** (services don't know about aiogram/fastapi)
4. **Scale gradually** (old and new code can coexist)
5. **Maintain cleanly** (clear separation of concerns)

Start using services in new code, and migrate old handlers gradually!

