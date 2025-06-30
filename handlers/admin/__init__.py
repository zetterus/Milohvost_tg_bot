from aiogram import Router

# Импортируем роутеры из наших новых модулей
from .admin_help_messages import router as admin_help_messages_router
from .admin_main_menu import router as admin_main_menu_router
from .admin_order_details import router as admin_order_details_router
from .admin_orders_all import router as admin_orders_all_router
from .admin_orders_search import router as admin_orders_search_router
from .admin_utils import router as admin_utils_router # Возможно, здесь тоже будут обработчики

# Импортируем AdminStates из admin_states.py внутри этого же пакета
from .admin_states import AdminStates

# Создаем главный роутер для АДМИНСКОГО функционала
admin_router = Router()

# Регистрируем все дочерние роутеры
admin_router.include_router(admin_help_messages_router)
admin_router.include_router(admin_main_menu_router)
admin_router.include_router(admin_order_details_router)
admin_router.include_router(admin_orders_all_router)
admin_router.include_router(admin_orders_search_router)
admin_router.include_router(admin_utils_router)

__all__ = ["admin_router", "AdminStates"]