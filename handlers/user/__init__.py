from aiogram import Router

# Импортируем роутеры из наших новых модулей
from .help import router as help_router
from .main_menu import router as main_menu_router
from .order_creation import router as order_creation_router
from .order_viewing import router as order_viewing_router

# Импортируем OrderStates из user_states.py внутри этого же пакета
from .user_states import OrderStates

# Создаем главный роутер для пользовательского функционала
user_router = Router()

# Регистрируем все дочерние роутеры
user_router.include_router(help_router)
user_router.include_router(main_menu_router)
user_router.include_router(order_creation_router)
user_router.include_router(order_viewing_router)

__all__ = ["user_router", "OrderStates"]
