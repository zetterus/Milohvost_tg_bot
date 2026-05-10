"""Bot setup - creates Bot, Dispatcher, registers middlewares and routers."""
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeDefault, BotCommandScopeAllGroupChats

from core.config import settings
from bot.middlewares.localization_middleware import LocalizationMiddleware
from bot.handlers import user_router, admin_router

logger = logging.getLogger(__name__)


async def set_commands(bot: Bot) -> None:
    """Register bot commands visible in Telegram menu."""
    commands = [
        BotCommand(command="start", description="Start bot"),
        BotCommand(command="admin", description="Admin panel"),
    ]
    try:
        # Clear old commands first
        await bot.set_my_commands([], scope=BotCommandScopeDefault())
        await bot.set_my_commands([], scope=BotCommandScopeAllPrivateChats())
        await bot.set_my_commands([], scope=BotCommandScopeAllGroupChats())
        # Set new commands
        await bot.set_my_commands(commands, scope=BotCommandScopeAllPrivateChats())
        logger.info("Bot commands registered")
    except Exception as e:
        logger.warning(f"Failed to set commands: {e}")


async def run_bot() -> None:
    """Initialize and run the bot with polling."""
    logging.basicConfig(
        level=settings.logging_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info("Starting bot...")

    storage = MemoryStorage()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())

    # Register middlewares
    dp.update.middleware(LocalizationMiddleware())

    # Register routers
    dp.include_router(user_router)
    dp.include_router(admin_router)

    # Setup commands
    await set_commands(bot)

    # Drop pending updates on start
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        logger.warning(f"Could not delete webhook: {e}")

    logger.info("Bot started, polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        logger.info("Bot session closed")

