"""Structured logging setup for the bot process.

Log records include standard fields (timestamp, level, logger name, message)
and optional `extra` dict fields for request-scoped context (e.g. user_id).
Call `setup_logging()` once at process startup before any other logging.
"""

import logging
import sys
from typing import Final

DEFAULT_FORMAT: Final[str] = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT: Final[str] = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with a single stream handler."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Avoid duplicate handlers when reloading in development.
    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)

    # Reduce noise from third-party libraries in production.
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger (e.g. `get_logger(__name__)`)."""
    return logging.getLogger(name)
