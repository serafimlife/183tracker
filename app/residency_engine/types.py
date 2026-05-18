"""Pure data types for residency calculations (no ORM/Telegram)."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class StayRecord:
    """Minimal stay interval for the residency engine."""

    entry_date: date
    exit_date: date | None
    country_code: str
    country_name: str
    stay_id: int | None = None
