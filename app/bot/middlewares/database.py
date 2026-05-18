"""Injects an async SQLAlchemy session into each update's handler `data` dict.

Handlers and services access the session via the `session` keyword argument:
    async def handler(message: Message, session: AsyncSession): ...

The session is committed on success and rolled back on exception.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_session_factory


class DatabaseMiddleware(BaseMiddleware):
    """Opens one DB session per incoming update."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        factory = get_session_factory()
        async with factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
