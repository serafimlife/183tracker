"""Rolling 365-day physical presence totals."""

from collections.abc import Sequence
from datetime import date, timedelta

from app.residency_engine.intervals import days_in_range_within
from app.residency_engine.types import StayRecord


def calculate_rolling_365_days(
    stays: Sequence[StayRecord],
    target_date: date,
    *,
    country_code: str | None = None,
) -> int:
    """Inclusive days in the 365-day window ending on `target_date`."""
    window_start = target_date - timedelta(days=364)
    window = (window_start, target_date)

    total = 0
    for stay in stays:
        if country_code is not None and stay.country_code != country_code:
            continue
        total += days_in_range_within(
            stay.entry_date,
            stay.exit_date,
            window,
            cap=target_date,
        )

    return total
