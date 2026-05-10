"""User handlers package."""
from aiogram import Router
from .start import router as start_router
from .order_creation import router as order_creation_router
from .order_viewing import router as order_viewing_router
from .settings import router as settings_router
from .help import router as help_router
user_router = Router()
user_router.include_router(start_router)
user_router.include_router(order_creation_router)
user_router.include_router(order_viewing_router)
user_router.include_router(settings_router)
user_router.include_router(help_router)
__all__ = ["user_router"]
