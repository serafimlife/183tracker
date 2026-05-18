"""Calendar-year physical presence totals."""

from collections.abc import Sequence
from datetime import date

from app.residency_engine.intervals import days_in_range_within
from app.residency_engine.types import StayRecord


def calculate_calendar_year_days(
    stays: Sequence[StayRecord],
    year: int,
    *,
    country_code: str | None = None,
    as_of: date | None = None,
) -> int:
    """Sum inclusive days in `year`, optionally filtered by country."""
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    reference = as_of or date.today()
    cap = min(year_end, reference)

    window = (year_start, year_end)
    total = 0

    for stay in stays:
        if country_code is not None and stay.country_code != country_code:
            continue
        total += days_in_range_within(
            stay.entry_date,
            stay.exit_date,
            window,
            cap=cap,
        )

    return total
