"""Tests for rolling 365-day window."""

from datetime import date

from app.residency_engine.rolling_window import calculate_rolling_365_days
from app.residency_engine.types import StayRecord


def _stay(entry: str, exit: str | None, code: str = "TH") -> StayRecord:
    e = date.fromisoformat(entry)
    x = date.fromisoformat(exit) if exit else None
    return StayRecord(e, x, code, "Thailand")


def test_single_stay_fully_inside_window() -> None:
    stays = [_stay("2026-01-01", "2026-03-01")]
    target = date(2026, 6, 1)
    assert calculate_rolling_365_days(stays, target) == 60


def test_stay_partially_before_window() -> None:
    stays = [_stay("2024-01-01", "2025-12-31")]
    target = date(2025, 6, 1)
    # Window: 2024-06-02 .. 2025-06-01 inclusive
    assert calculate_rolling_365_days(stays, target) == 365


def test_active_stay_to_target_date() -> None:
    stays = [_stay("2026-01-01", None)]
    target = date(2026, 3, 1)
    assert calculate_rolling_365_days(stays, target) == 60


def test_multiple_stays_summed() -> None:
    stays = [
        _stay("2025-12-01", "2025-12-31"),
        _stay("2026-01-01", "2026-01-31"),
    ]
    target = date(2026, 6, 1)
    assert calculate_rolling_365_days(stays, target, country_code="TH") == 62
