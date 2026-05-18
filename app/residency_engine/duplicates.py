"""Exact duplicate stay detection (pure functions)."""

from collections.abc import Sequence
from datetime import date

from app.residency_engine.types import StayRecord


def find_duplicate_entry(
    stays: Sequence[StayRecord],
    country_code: str,
    entry_date: date,
) -> StayRecord | None:
    """Same country and entry date already recorded."""
    for stay in stays:
        if stay.country_code == country_code and stay.entry_date == entry_date:
            return stay
    return None


def find_duplicate_exit(
    stays: Sequence[StayRecord],
    country_code: str,
    exit_date: date,
) -> StayRecord | None:
    """Same country and exit date already recorded on a closed stay."""
    for stay in stays:
        if (
            stay.country_code == country_code
            and stay.exit_date is not None
            and stay.exit_date == exit_date
        ):
            return stay
    return None
