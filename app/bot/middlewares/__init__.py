"""Aiogram middlewares — cross-cutting concerns applied before handlers.

Register middleware on the dispatcher or on specific routers in `main.py`.
Order matters: outer middleware runs first on the way in, last on the way out.
"""

from app.bot.middlewares.database import DatabaseMiddleware

__all__ = ["DatabaseMiddleware"]
