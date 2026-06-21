"""Country-to-country transition rules (pure functions)."""

from collections.abc import Sequence
from datetime import date

from app.residency_engine.types import StayRecord


def find_open_stay_other_country(
    stays: Sequence[StayRecord],
    new_country_code: str,
) -> StayRecord | None:
    """Return the latest open stay in a country different from `new_country_code`."""
    candidates = [
        s for s in stays if s.exit_date is None and s.country_code != new_country_code
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.entry_date)


def can_transition_on_date(open_stay: StayRecord, entry_date: date) -> bool:
    """Entry date must be on or after the open stay's entry (same-day exit allowed)."""
    return entry_date >= open_stay.entry_date
