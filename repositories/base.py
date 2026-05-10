"""Abstract base repository with common CRUD operations."""
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
T = TypeVar("T")
class AbstractRepository(ABC, Generic[T]):
    """Base repository class providing common async CRUD patterns."""
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
    @abstractmethod
    async def create(self, **kwargs) -> T:
        """Create a new entity."""
        pass
    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[T]:
        """Get entity by ID."""
        pass
    @abstractmethod
    async def get_all(self) -> List[T]:
        """Get all entities."""
        pass
    @abstractmethod
    async def update(self, id: int, **kwargs) -> bool:
        """Update an entity."""
        pass
    @abstractmethod
    async def delete(self, id: int) -> bool:
        """Delete an entity."""
        pass
