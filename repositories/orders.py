"""Order repository - data access layer for orders."""
import logging
from typing import Optional, Tuple, List
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func as sql_func
from models import Order
from .base import AbstractRepository
logger = logging.getLogger(__name__)
class OrderRepository(AbstractRepository[Order]):
    """Repository for Order entities."""
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
    async def create(
        self,
        user_id: int,
        username: str,
        order_text: str,
        full_name: Optional[str] = None,
        delivery_address: Optional[str] = None,
        payment_method: Optional[str] = None,
        contact_phone: Optional[str] = None,
        delivery_notes: Optional[str] = None,
        status: str = "new",
    ) -> Order:
        """Create a new order."""
        new_order = Order(
            user_id=user_id,
            username=username,
            order_text=order_text,
            full_name=full_name,
            delivery_address=delivery_address,
            payment_method=payment_method,
            contact_phone=contact_phone,
            delivery_notes=delivery_notes,
            status=status,
        )
        self._session.add(new_order)
        await self._session.flush()
        await self._session.refresh(new_order)
        logger.info(f"New order ID {new_order.id} created for user {user_id}")
        return new_order
    async def get_by_id(self, order_id: int) -> Optional[Order]:
        """Get order by ID."""
        stmt = select(Order).where(Order.id == order_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
    async def get_all(self, offset: int = 0, limit: int = 10) -> Tuple[List[Order], int]:
        """Get all orders with pagination."""
        count_stmt = select(func.count()).select_from(Order)
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            select(Order)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        orders = result.scalars().all()
        return orders, total
    async def get_paginated(self, offset: int = 0, limit: int = 10) -> Tuple[List[Order], int]:
        """Alias for get_all with pagination."""
        return await self.get_all(offset, limit)
    async def search(self, query: str, offset: int = 0, limit: int = 10) -> Tuple[List[Order], int]:
        """Search orders by ID, username, or order text."""
        search_pattern = f"%{query.lower()}%"
        try:
            search_id = int(query)
        except ValueError:
            search_id = None
        conditions = []
        if search_id is not None:
            conditions.append(Order.id == search_id)
        conditions.extend([
            func.lower(Order.username).like(search_pattern),
            func.lower(Order.order_text).like(search_pattern),
            func.lower(Order.full_name).like(search_pattern),
            func.lower(Order.delivery_address).like(search_pattern),
            func.lower(Order.contact_phone).like(search_pattern),
            func.lower(Order.delivery_notes).like(search_pattern),
        ])
        combined_condition = or_(*conditions)
        count_stmt = select(func.count()).select_from(Order).where(combined_condition)
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            select(Order)
            .where(combined_condition)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        orders = result.scalars().all()
        return orders, total
    async def get_user_orders(self, user_id: int, offset: int = 0, limit: int = 5) -> Tuple[List[Order], int]:
        """Get orders for a specific user with pagination."""
        count_stmt = select(func.count()).select_from(Order).where(Order.user_id == user_id)
        total = (await self._session.execute(count_stmt)).scalar_one()
        stmt = (
            select(Order)
            .where(Order.user_id == user_id)
            .order_by(Order.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        orders = result.scalars().all()
        return orders, total
    async def update_status(self, order_id: int, new_status: str) -> bool:
        """Update order status."""
        order = await self.get_by_id(order_id)
        if order:
            order.status = new_status
            order.updated_at = sql_func.now()
            logger.info(f"Order {order_id} status updated to {new_status}")
            return True
        logger.warning(f"Order {order_id} not found for status update")
        return False
    async def update_text(self, order_id: int, new_text: str) -> bool:
        """Update order text."""
        order = await self.get_by_id(order_id)
        if order:
            order.order_text = new_text
            order.updated_at = sql_func.now()
            logger.info(f"Order {order_id} text updated")
            return True
        logger.warning(f"Order {order_id} not found for text update")
        return False
    async def update(self, order_id: int, **kwargs) -> bool:
        """Update order with arbitrary kwargs."""
        order = await self.get_by_id(order_id)
        if order:
            for key, value in kwargs.items():
                if hasattr(order, key):
                    setattr(order, key, value)
            order.updated_at = sql_func.now()
            return True
        return False
    async def delete(self, order_id: int) -> bool:
        """Delete order by ID."""
        order = await self.get_by_id(order_id)
        if order:
            await self._session.delete(order)
            logger.info(f"Order {order_id} deleted")
            return True
        logger.warning(f"Order {order_id} not found for deletion")
        return False
