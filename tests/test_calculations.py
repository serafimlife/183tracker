"""Tests for stay duration calculations."""

from datetime import date

from app.residency_engine.calculations import stay_duration_days


def test_same_day_stay() -> None:
    assert (
        stay_duration_days(date(2026, 3, 1), date(2026, 3, 1), as_of=date(2026, 3, 1))
        == 1
    )


def test_open_stay_uses_as_of() -> None:
    assert stay_duration_days(date(2026, 1, 1), None, as_of=date(2026, 3, 1)) == 60
