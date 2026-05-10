"""Order service - business logic for orders."""
import logging
from dataclasses import dataclass
from typing import Optional
from core import InvalidPhoneError, OrderValidationError, PHONE_NUMBER_REGEX
from models import Order
from repositories.orders import OrderRepository
from repositories.users import UserRepository
logger = logging.getLogger(__name__)
@dataclass
class OrderCreateData:
    """Validated order creation data."""
    user_id: int
    username: str
    order_text: str
    full_name: Optional[str] = None
    delivery_address: Optional[str] = None
    payment_method: Optional[str] = None
    contact_phone: Optional[str] = None
    delivery_notes: Optional[str] = None
    status: str = "new"
class OrderService:
    """Service layer for order business logic."""
    def __init__(self, order_repo: OrderRepository, user_repo: UserRepository) -> None:
        self._order_repo = order_repo
        self._user_repo = user_repo
    async def create_order(self, data: OrderCreateData) -> Order:
        """Create a new order with validation."""
        if data.contact_phone and not PHONE_NUMBER_REGEX.fullmatch(data.contact_phone):
            raise InvalidPhoneError(data.contact_phone)
        if not data.order_text or not data.order_text.strip():
            raise OrderValidationError("Order text is required", "order_text")
        order = await self._order_repo.create(
            user_id=data.user_id,
            username=data.username,
            order_text=data.order_text,
            full_name=data.full_name,
            delivery_address=data.delivery_address,
            payment_method=data.payment_method,
            contact_phone=data.contact_phone,
            delivery_notes=data.delivery_notes,
            status=data.status,
        )
        return order
    async def get_order(self, order_id: int) -> Optional[Order]:
        """Get order by ID."""
        return await self._order_repo.get_by_id(order_id)
    async def get_all_orders(self, offset: int = 0, limit: int = 10):
        """Get all orders with pagination."""
        return await self._order_repo.get_all(offset, limit)
    async def search_orders(self, query: str, offset: int = 0, limit: int = 10):
        """Search orders."""
        return await self._order_repo.search(query, offset, limit)
    async def get_user_orders(self, user_id: int, offset: int = 0, limit: int = 5):
        """Get orders for a specific user."""
        return await self._order_repo.get_user_orders(user_id, offset, limit)
    async def update_order_status(self, order_id: int, status: str) -> bool:
        """Update order status."""
        return await self._order_repo.update_status(order_id, status)
    async def update_order_text(self, order_id: int, text: str) -> bool:
        """Update order text."""
        return await self._order_repo.update_text(order_id, text)
    async def delete_order(self, order_id: int) -> bool:
        """Delete order."""
        return await self._order_repo.delete(order_id)
