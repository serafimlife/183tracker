"""Async SQLAlchemy engine and session factory.

Lifecycle:
  1. `init_db(url)` — called from bot startup handler
  2. Per-update sessions — injected by `DatabaseMiddleware` into handler `data`
  3. `close_db()` — called from bot shutdown handler

Repositories receive an `AsyncSession` per request; they never create engines.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Module-level singletons set during startup.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the active session factory (raises if DB not initialized)."""
    if _session_factory is None:
        raise RuntimeError("Database is not initialized. Call init_db() first.")
    return _session_factory


async def init_db(database_url: str, *, echo: bool = False) -> None:
    """Create async engine and session factory."""
    global _engine, _session_factory

    _engine = create_async_engine(
        database_url,
        echo=echo,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def close_db() -> None:
    """Dispose engine and clear module state."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def create_tables() -> None:
    """Create tables from models (dev convenience; use Alembic in production)."""
    from app.models import Base  # noqa: PLC0415 — avoid import cycles at module load

    if _engine is None:
        raise RuntimeError("Database is not initialized. Call init_db() first.")

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Standalone session generator (e.g. scripts); handlers use middleware instead."""
    factory = get_session_factory()
    async with factory() as session:
        yield session
