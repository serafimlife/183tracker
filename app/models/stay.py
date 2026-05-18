"""Stay ORM model — country presence periods."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Stay(Base):
    """A period spent in a country (entry date required; exit optional until /out)."""

    __tablename__ = "stays"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        index=True,
    )
    country_code: Mapped[str] = mapped_column(String(2), index=True)
    country_name: Mapped[str] = mapped_column(String(255))
    entry_date: Mapped[date] = mapped_column(Date)
    exit_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
