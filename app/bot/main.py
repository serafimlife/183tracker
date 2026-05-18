"""Bot entry point — wires aiogram, database, middleware, and lifecycle hooks.

Architecture (top → bottom):
  main.py          → process bootstrap, polling
  handlers/        → Telegram commands/callbacks (thin)
  services/        → business logic
  repositories/    → SQLAlchemy data access
  models/          → ORM entities
  database/        → engine and session factory
  residency_engine/→ pure domain calculations (no Telegram/DB)
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.config import get_settings
from app.bot.logger import get_logger, setup_logging
from app.bot.middlewares import DatabaseMiddleware
from app.database.session import close_db, create_tables, init_db
from app.handlers import root_router

logger = get_logger(__name__)


async def on_startup(bot: Bot) -> None:
    """Runs once when polling starts — initialize shared resources."""
    settings = get_settings()
    await init_db(settings.database_url)
    # Dev convenience: create tables if migrations are not set up yet.
    await create_tables()
    me = await bot.get_me()
    logger.info("Bot started as @%s (id=%s)", me.username, me.id)


async def on_shutdown(bot: Bot) -> None:
    """Runs once when polling stops — release shared resources."""
    await close_db()
    logger.info("Bot shutdown complete")


def create_dispatcher() -> Dispatcher:
    """Build dispatcher with middleware and routers.

    Middleware registration order (first registered = outermost):
      - DatabaseMiddleware — injects `session` into handler data
      - Add logging, throttling, i18n, etc. here as the project grows
    """
    # FSM storage: MemoryStorage for dev; swap for Redis in multi-instance production.
    dp = Dispatcher(storage=MemoryStorage())

    # Outermost middleware wraps every update.
    dp.update.middleware(DatabaseMiddleware())

    # Example: per-router middleware for a feature group
    # dp.message.middleware(SomeMiddleware())

    dp.include_router(root_router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    return dp


def create_bot() -> Bot:
    """Construct Bot client with default properties."""
    settings = get_settings()
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def run_async() -> None:
    """Main async entry — configure logging and start long polling."""
    settings = get_settings()
    setup_logging(settings.log_level)

    bot = create_bot()
    dp = create_dispatcher()

    logger.info("Starting long polling…")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def run() -> None:
    """Sync wrapper for `python -m app.bot.main` and console scripts."""
    try:
        asyncio.run(run_async())
    except (KeyboardInterrupt, SystemExit):
        logging.getLogger(__name__).info("Interrupted by user")


if __name__ == "__main__":
    run()
