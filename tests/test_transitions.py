"""Tests for country transition detection."""

from datetime import date

from app.residency_engine.transitions import (
    can_transition_on_date,
    find_open_stay_other_country,
)
from app.residency_engine.types import StayRecord
from app.residency_engine.validation import find_overlapping_stay


def _stay(
    entry: str,
    exit: str | None,
    code: str,
    stay_id: int,
) -> StayRecord:
    return StayRecord(
        date.fromisoformat(entry),
        date.fromisoformat(exit) if exit else None,
        code,
        "Country",
        stay_id,
    )


def test_find_open_stay_other_country() -> None:
    stays = [
        _stay("2026-02-25", None, "ID", 1),
        _stay("2026-01-01", "2026-01-31", "TH", 2),
    ]
    found = find_open_stay_other_country(stays, "TH")
    assert found is not None
    assert found.country_code == "ID"


def test_transition_not_overlap_with_open_stay() -> None:
    """After closing prior stay on entry day, no overlap remains."""
    stays = [_stay("2026-02-25", None, "ID", 1)]
    entry = date(2026, 5, 17)
    assert can_transition_on_date(stays[0], entry)
    # Same-day boundary: excluded open stay will be closed on entry date.
    conflict_excl = find_overlapping_stay(
        stays, entry, None, exclude_stay_id=1, as_of=date(2026, 12, 31)
    )
    assert conflict_excl is None


def test_overlap_is_not_transition() -> None:
    """Closed Indonesia + overlapping Thailand entry is overlap, not transition."""
    stays = [_stay("2026-01-01", "2026-01-30", "ID", 1)]
    entry = date(2026, 1, 29)
    assert find_open_stay_other_country(stays, "TH") is None
    assert (
        find_overlapping_stay(
            stays, entry, date(2026, 2, 10), as_of=date(2026, 2, 10)
        )
        is not None
    )
