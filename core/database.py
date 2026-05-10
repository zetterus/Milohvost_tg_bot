"""Database infrastructure - engine, session factory, and session management."""
import logging
from contextlib import asynccontextmanager
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, AsyncEngine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.sqlite.aiosqlite import AsyncAdapt_aiosqlite_connection
from .config import settings
logger = logging.getLogger(__name__)
def _sqlite_unicode_lower(value: str | None) -> str | None:
    """Custom SQLite function for proper Unicode lowercase conversion."""
    if value is None:
        return None
    return value.lower()
# Async engine for database
engine: AsyncEngine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.database_name}",
    echo=False,
    pool_pre_ping=True
)
# Async session factory
AsyncSessionLocal = sessionmaker(
    expire_on_commit=False,
    class_=AsyncSession,
    bind=engine
)
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, _connection_record):
    """Register custom SQLite functions and pragmas."""
    if isinstance(dbapi_connection, AsyncAdapt_aiosqlite_connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        dbapi_connection.create_function("LOWER", 1, _sqlite_unicode_lower)
        cursor.close()
@asynccontextmanager
async def get_db_session():
    """Async context manager for database sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database transaction error: {e}")
            await session.rollback()
            raise
