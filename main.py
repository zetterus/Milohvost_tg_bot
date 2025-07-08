import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.memory import SimpleEventIsolation # <-- Используем ваш импорт SimpleEventIsolation
from aiogram.fsm.middleware import FSMContextMiddleware

from config import BOT_TOKEN, LOGGING_LEVEL
from db import create_tables_async
from handlers import user_router, admin_router
from middlewares.localization_middleware import LocalizationMiddleware

# Настройка логирования
logging.basicConfig(level=LOGGING_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    """
    Основная функция для запуска Telegram бота.
    Выполняет инициализацию базы данных, бота и диспетчера,
    регистрирует хэндлеры и запускает поллинг.
    """
    logger.info("Запуск бота...")

    try:
        # Инициализируем базу данных: создаем таблицы, если они не существуют
        await create_tables_async()
        logger.info("База данных успешно инициализирована.")
    except Exception as db_error:
        logger.exception(f"Критическая ошибка при инициализации базы данных: {db_error}")
        return

    # Инициализируем хранилище FSM
    storage = MemoryStorage()

    # Инициализируем бота
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Инициализируем диспетчер
    # Передача storage в конструктор автоматически добавляет FSMContextMiddleware.
    # events_isolation также явно передается.
    dp = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())

    # Добавляем FSMContextMiddleware на уровень update, чтобы state, storage и storage_key
    # были доступны в data для LocalizationMiddleware и других middleware/хендлеров.
    # Согласно вашим наблюдениям, FSMContextMiddleware требует storage и events_isolation.
    dp.update.middleware(FSMContextMiddleware(storage=storage, events_isolation=SimpleEventIsolation())) # <-- ИСПРАВЛЕНО ЗДЕСЬ

    # Добавляем наше кастомное middleware для локализации
    dp.update.middleware(LocalizationMiddleware())

    # Регистрируем роутеры, которые содержат все хэндлеры
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Удаляем любые предыдущие вебхуки (если были) и игнорируем накопившиеся обновления
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхуки удалены, ожидающие обновления пропущены.")
    except Exception as webhook_error:
        logger.warning(f"Не удалось удалить вебхуки или пропустить обновления (возможно, их не было): {webhook_error}")

    logger.info("Бот запущен. Начинаю поллинг...")
    try:
        await dp.start_polling(bot)
    except Exception as polling_error:
        logger.exception(f"Критическая ошибка при поллинге бота: {polling_error}")
    finally:
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную (KeyboardInterrupt).")
    except Exception as e:
        logger.critical(f"Произошла непредвиденная критическая ошибка: {e}", exc_info=True)
