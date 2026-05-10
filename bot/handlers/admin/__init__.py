"""Admin handlers package."""
from aiogram import Router
from .main_menu import router as main_menu_router
from .orders import router as orders_router
from .help_messages import router as help_messages_router
admin_router = Router()
admin_router.include_router(main_menu_router)
admin_router.include_router(orders_router)
admin_router.include_router(help_messages_router)
__all__ = ["admin_router"]
