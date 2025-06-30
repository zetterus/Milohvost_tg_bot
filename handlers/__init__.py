# handlers/__init__.py

from .user import user_router # Импортируем главный user_router из подпакета
from .admin import admin_router # Импортируем главный admin_router из подпакета

# Вы можете также экспортировать их, чтобы было удобно импортировать в main.py
__all__ = ["user_router", "admin_router"]