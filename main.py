# main.py
import asyncio
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN, LOGGING_LEVEL
from db import create_tables_async
from handlers import user_router, admin_router


# Настройка логирования
logging.basicConfig(level=LOGGING_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """
    Основная функция для запуска бота.
    """
    logger.info("Запуск бота...")

    # Инициализируем базу данных
    await create_tables_async()  # асинхронное создание таблиц

    # Инициализируем бота с дефолтными свойствами
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Регистрируем роутеры
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Удаляем вебхуки и пропускаем все накопившиеся обновления
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Бот запущен. Ожидание обновлений...")
    # Запускаем поллинг
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную.")
    except Exception as e:
        logger.error(f"Произошла непредвиденная ошибка: {e}")
