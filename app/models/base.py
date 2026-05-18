"""SQLAlchemy declarative base shared by all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Subclass for every table model in `app.models`."""

    pass
