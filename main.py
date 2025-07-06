import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN, LOGGING_LEVEL
from db import create_tables_async  # Импортируем функцию для создания таблиц
from handlers import user_router, admin_router  # Импортируем роутеры

# Настройка логирования
# Устанавливаем базовый уровень логирования и формат
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
        # Завершаем программу, если БД не инициализирована
        return

    storage = MemoryStorage()

    # Инициализируем бота с токеном и дефолтными свойствами
    # parse_mode=ParseMode.HTML устанавливается по умолчанию для всех сообщений
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    # Инициализируем диспетчер для обработки входящих обновлений
    dp = Dispatcher(storage=storage) # Привязываем хранилище к диспетчеру

    # Регистрируем роутеры, которые содержат все хэндлеры
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Удаляем любые предыдущие вебхуки (если были) и игнорируем накопившиеся обновления
    # Это важно для поллинга, чтобы бот не обрабатывал старые сообщения после перезапуска
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхуки удалены, ожидающие обновления пропущены.")
    except Exception as webhook_error:
        logger.warning(f"Не удалось удалить вебхуки или пропустить обновления (возможно, их не было): {webhook_error}")

    logger.info("Бот запущен. Начинаю поллинг...")
    # Запускаем поллинг: бот начинает получать и обрабатывать обновления
    try:
        await dp.start_polling(bot)
    except Exception as polling_error:
        logger.exception(f"Критическая ошибка при поллинге бота: {polling_error}")
    finally:
        # Корректно закрываем сессию бота при завершении работы
        await bot.session.close()
        logger.info("Сессия бота закрыта.")


if __name__ == "__main__":
    # Запускаем основную асинхронную функцию
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Обработка остановки бота пользователем (Ctrl+C)
        logger.info("Бот остановлен вручную с клавиатуры (KeyboardInterrupt).")
    except Exception as e:
        # Общая обработка любых других непредвиденных ошибок при запуске/выполнении main
        logger.critical(f"Произошла непредвиденная критическая ошибка при запуске бота: {e}", exc_info=True)