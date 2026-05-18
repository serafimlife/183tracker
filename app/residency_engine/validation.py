"""Stay overlap validation (pure functions)."""

from collections.abc import Sequence
from datetime import date

from app.residency_engine.intervals import has_overlap
from app.residency_engine.types import StayRecord


def find_overlapping_stay(
    stays: Sequence[StayRecord],
    entry_date: date,
    exit_date: date | None,
    *,
    exclude_stay_id: int | None = None,
    as_of: date | None = None,
) -> StayRecord | None:
    """Return the first conflicting stay, or None if the interval is valid."""
    reference = as_of or date.today()

    for stay in stays:
        if exclude_stay_id is not None and stay.stay_id == exclude_stay_id:
            continue
        if has_overlap(
            entry_date,
            exit_date,
            stay.entry_date,
            stay.exit_date,
            cap_a=reference,
            cap_b=reference,
        ):
            return stay
    return None
