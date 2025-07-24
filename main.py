import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.memory import SimpleEventIsolation
from aiogram.fsm.middleware import FSMContextMiddleware
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeDefault, BotCommandScopeAllGroupChats # Импорт для команд меню

from config import BOT_TOKEN, LOGGING_LEVEL
from db import create_tables_async
from handlers import user_router, admin_router
from middlewares.localization_middleware import LocalizationMiddleware

# Настройка логирования
logging.basicConfig(level=LOGGING_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def set_default_commands(bot: Bot):
    """
    Устанавливает стандартные команды для бота.
    Эти команды будут отображаться в меню Telegram.
    """
    commands = [
        BotCommand(command="start", description="Start bot"),
        BotCommand(command="admin", description="For admins only"),
        # Добавьте сюда все актуальные команды, которые вы хотите видеть в меню
        # Например, если у вас есть команда /admin для админов, но вы не хотите,
        # чтобы она была в общем меню, не добавляйте ее сюда.
    ]
    try:
        await bot.set_my_commands(
            commands,
            scope=BotCommandScopeAllPrivateChats() # Команды будут видны во всех личных чатах
        )
        logger.info("Команды бота успешно установлены.")
    except Exception as e:
        logger.error(f"Ошибка при установке команд бота: {e}")


async def clear_all_commands(bot: Bot):
    """
    Удаляет все команды из меню бота для всех личных чатов.
    Полезно для очистки старых команд во время разработки.
    """
    try:
        await bot.set_my_commands([], scope=BotCommandScopeDefault())
        await bot.set_my_commands([], scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
        logger.info("Все команды бота успешно удалены.")
    except Exception as e:
        logger.error(f"Ошибка при удалении команд бота: {e}")


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
    dp = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())

    # Добавляем FSMContextMiddleware на уровень update
    dp.update.middleware(FSMContextMiddleware(storage=storage, events_isolation=SimpleEventIsolation()))

    # Добавляем наше кастомное middleware для локализации
    dp.update.middleware(LocalizationMiddleware())

    # Регистрируем роутеры, которые содержат все хэндлеры
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # ДОБАВЛЕНО: Очистка всех команд перед установкой новых (для разработки/отладки)
    await clear_all_commands(bot)

    # Установка команд меню при запуске бота
    await set_default_commands(bot)

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
