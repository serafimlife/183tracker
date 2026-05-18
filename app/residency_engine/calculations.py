"""Core stay duration helpers."""

from datetime import date

from app.residency_engine.intervals import inclusive_days


def stay_duration_days(
    entry_date: date,
    exit_date: date | None,
    *,
    as_of: date,
) -> int:
    """Inclusive days for one stay; open stays end on `as_of`."""
    end = exit_date if exit_date is not None else as_of
    if end < entry_date:
        return 0
    return inclusive_days(entry_date, end)
