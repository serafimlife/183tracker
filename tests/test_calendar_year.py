"""Tests for calendar-year day counting."""

from datetime import date

from app.residency_engine.calendar_year import calculate_calendar_year_days
from app.residency_engine.types import StayRecord


def _stay(entry: str, exit: str | None, code: str = "ID") -> StayRecord:
    e = date.fromisoformat(entry)
    x = date.fromisoformat(exit) if exit else None
    return StayRecord(e, x, code, "Country")


def test_single_stay_in_year() -> None:
    stays = [_stay("2026-03-01", "2026-03-31")]
    assert calculate_calendar_year_days(stays, 2026, as_of=date(2026, 12, 31)) == 31


def test_year_boundary_split() -> None:
    stays = [_stay("2025-12-20", "2026-01-10")]
    assert calculate_calendar_year_days(stays, 2025, as_of=date(2026, 12, 31)) == 12
    assert calculate_calendar_year_days(stays, 2026, as_of=date(2026, 12, 31)) == 10


def test_active_stay_capped_at_as_of() -> None:
    stays = [_stay("2026-01-01", None)]
    assert calculate_calendar_year_days(stays, 2026, as_of=date(2026, 3, 1)) == 60


def test_leap_year_february() -> None:
    stays = [_stay("2024-02-01", "2024-02-29")]
    assert calculate_calendar_year_days(stays, 2024, as_of=date(2024, 12, 31)) == 29


def test_multiple_stays_same_country() -> None:
    stays = [
        _stay("2026-01-01", "2026-01-15"),
        _stay("2026-02-01", "2026-02-10"),
    ]
    assert (
        calculate_calendar_year_days(
            stays, 2026, country_code="ID", as_of=date(2026, 12, 31)
        )
        == 25
    )
