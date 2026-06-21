"""Schengen Area 90/180-day rule calculations."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.residency_engine.intervals import days_in_range_within
from app.residency_engine.types import StayRecord

# ISO 3166-1 alpha-2 codes for Schengen Area member states as of June 2026.
# Review periodically — membership can change (Bulgaria/Romania joined 2024, Croatia 2023).
SCHENGEN_CODES: frozenset[str] = frozenset(
    {
        "AT",  # Austria
        "BE",  # Belgium
        "BG",  # Bulgaria
        "HR",  # Croatia
        "CZ",  # Czech Republic
        "DK",  # Denmark
        "EE",  # Estonia
        "FI",  # Finland
        "FR",  # France
        "DE",  # Germany
        "GR",  # Greece
        "HU",  # Hungary
        "IS",  # Iceland
        "IT",  # Italy
        "LV",  # Latvia
        "LI",  # Liechtenstein
        "LT",  # Lithuania
        "LU",  # Luxembourg
        "MT",  # Malta
        "NL",  # Netherlands
        "NO",  # Norway
        "PL",  # Poland
        "PT",  # Portugal
        "RO",  # Romania
        "SK",  # Slovakia
        "SI",  # Slovenia
        "ES",  # Spain
        "SE",  # Sweden
        "CH",  # Switzerland
    }
)

_WINDOW_DAYS = 180
_MAX_DAYS = 90


@dataclass(frozen=True, slots=True)
class SchengenResult:
    """90/180-day rule status for a user."""

    days_used: int
    days_remaining: int
    # First date user can (re-)enter Schengen without exceeding the cap.
    # None when days_remaining > 0 (cap not reached).
    next_free_date: date | None


def calculate_schengen_days(stays: Sequence[StayRecord], as_of: date) -> int:
    """Combined Schengen days in the 180-day window ending on as_of."""
    window_start = as_of - timedelta(days=_WINDOW_DAYS - 1)
    window = (window_start, as_of)
    return sum(
        days_in_range_within(s.entry_date, s.exit_date, window, cap=as_of)
        for s in stays
        if s.country_code.upper() in SCHENGEN_CODES
    )


def _count_window_days(
    stays: Sequence[StayRecord], as_of: date, *, stay_cap: date
) -> int:
    """Days in the 180-day window ending on as_of; active stays capped at stay_cap."""
    window_start = as_of - timedelta(days=_WINDOW_DAYS - 1)
    window = (window_start, as_of)
    return sum(
        days_in_range_within(s.entry_date, s.exit_date, window, cap=stay_cap)
        for s in stays
    )


def _next_free_date(stays: Sequence[StayRecord], as_of: date) -> date | None:
    """First future date when the preceding 180-day window drops below the 90-day cap.

    Returns None when already under the cap. Assumes no new Schengen entries after
    as_of (active stays are capped there).
    """
    if _count_window_days(stays, as_of, stay_cap=as_of) < _MAX_DAYS:
        return None
    for offset in range(1, _WINDOW_DAYS + 1):
        candidate = as_of + timedelta(days=offset)
        if _count_window_days(stays, candidate, stay_cap=as_of) < _MAX_DAYS:
            return candidate
    return None


def schengen_status(stays: Sequence[StayRecord], as_of: date) -> SchengenResult:
    """Compute 90/180-day Schengen status as of the given date."""
    schengen_stays = [s for s in stays if s.country_code.upper() in SCHENGEN_CODES]
    days_used = _count_window_days(schengen_stays, as_of, stay_cap=as_of)
    days_remaining = max(0, _MAX_DAYS - days_used)
    next_free = _next_free_date(schengen_stays, as_of) if days_remaining == 0 else None
    return SchengenResult(
        days_used=days_used,
        days_remaining=days_remaining,
        next_free_date=next_free,
    )
