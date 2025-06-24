# bot.py
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import init_db
import handlers.user as user_handlers
import handlers.admin as admin_handlers

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

async def main():
    """Основная функция для запуска бота."""
    init_db() # Инициализация базы данных при старте

    # Регистрируем роутеры из отдельных модулей
    dp.include_router(admin_handlers.admin_router)
    dp.include_router(user_handlers.user_router)

    # Установка команд меню (можно также через BotFather)
    await bot.set_my_commands([
        types.BotCommand(command="start", description="Начать работу с ботом"),
        types.BotCommand(command="help", description="Получить помощь"),
        types.BotCommand(command="myorders", description="Показать мои заказы"),
        types.BotCommand(command="admin", description="Панель администратора") # Добавим и для админа, если еще нет
    ])

    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())