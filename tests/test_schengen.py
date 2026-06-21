"""Tests for Schengen 90/180-day sliding-window calculations."""

from datetime import date, timedelta

import pytest

from app.residency_engine.schengen import (
    SCHENGEN_CODES,
    SchengenResult,
    _next_free_date,
    calculate_schengen_days,
    schengen_status,
)
from app.residency_engine.types import StayRecord

# Fixed reference date used throughout — 180-day window: [2025-12-24, 2026-06-21]
TODAY = date(2026, 6, 21)
WINDOW_START = TODAY - timedelta(days=179)  # 2025-12-24


def _stay(
    entry: str,
    exit: str | None = None,
    *,
    code: str = "FR",
    name: str = "France",
) -> StayRecord:
    return StayRecord(
        entry_date=date.fromisoformat(entry),
        exit_date=date.fromisoformat(exit) if exit else None,
        country_code=code,
        country_name=name,
    )


class TestSchengenCodes:
    def test_29_members(self) -> None:
        assert len(SCHENGEN_CODES) == 29

    def test_known_members_present(self) -> None:
        for code in ("FR", "DE", "IT", "ES", "NL", "CH", "NO", "IS", "LI"):
            assert code in SCHENGEN_CODES

    def test_non_schengen_excluded(self) -> None:
        # Cyprus, Ireland, UK are NOT Schengen
        for code in ("CY", "IE", "GB"):
            assert code not in SCHENGEN_CODES

    def test_recent_additions_present(self) -> None:
        # Bulgaria and Romania joined 2024, Croatia 2023
        for code in ("BG", "RO", "HR"):
            assert code in SCHENGEN_CODES


class TestCalculateSchengenDays:
    def test_single_stay_fully_inside_window(self) -> None:
        stays = [_stay("2026-01-10", "2026-01-20")]
        assert calculate_schengen_days(stays, TODAY) == 11

    def test_stay_partially_outside_window_left(self) -> None:
        # Stay starts before window_start (2025-12-24)
        stays = [_stay("2025-12-20", "2025-12-28")]
        # Only 2025-12-24 to 2025-12-28 = 5 days inside window
        assert calculate_schengen_days(stays, TODAY) == 5

    def test_stay_entirely_outside_window(self) -> None:
        stays = [_stay("2025-06-01", "2025-06-10")]
        assert calculate_schengen_days(stays, TODAY) == 0

    def test_multiple_schengen_countries_combined(self) -> None:
        stays = [
            _stay("2026-01-01", "2026-01-15", code="FR", name="France"),  # 15 days
            _stay("2026-02-01", "2026-02-10", code="DE", name="Germany"),  # 10 days
            _stay("2026-03-01", "2026-03-05", code="IT", name="Italy"),  # 5 days
        ]
        assert calculate_schengen_days(stays, TODAY) == 30

    def test_non_schengen_excluded(self) -> None:
        stays = [
            _stay("2026-01-01", "2026-01-10", code="TH", name="Thailand"),
            _stay("2026-01-01", "2026-01-10", code="US", name="United States"),
            _stay("2026-01-01", "2026-01-10", code="GB", name="United Kingdom"),
        ]
        assert calculate_schengen_days(stays, TODAY) == 0

    def test_mixed_schengen_and_non_schengen(self) -> None:
        stays = [
            _stay("2026-01-01", "2026-01-10", code="FR", name="France"),  # 10
            _stay("2026-01-01", "2026-01-10", code="TH", name="Thailand"),  # excluded
        ]
        assert calculate_schengen_days(stays, TODAY) == 10

    def test_active_stay_capped_at_as_of(self) -> None:
        # Active stay started 2026-06-01 — should count only up to TODAY (June 21)
        stays = [_stay("2026-06-01")]  # no exit_date
        # 2026-06-01 to 2026-06-21 inclusive = 21 days
        assert calculate_schengen_days(stays, TODAY) == 21

    def test_active_stay_not_counting_future_days(self) -> None:
        # Active stay far in the past — should not inflate count beyond today
        stays = [_stay("2026-01-01")]
        # 2026-01-01 to TODAY = 172 days, but capped at 90 max anyway
        # Just verify it's not more than days-to-today
        days_to_today = (TODAY - date(2026, 1, 1)).days + 1  # 172 days
        # But window starts 2025-12-24, so full overlap from 2026-01-01 to TODAY
        assert calculate_schengen_days(stays, TODAY) == days_to_today

    def test_lowercase_country_code_treated_case_insensitively(self) -> None:
        stays = [_stay("2026-01-01", "2026-01-10", code="fr", name="France")]
        assert calculate_schengen_days(stays, TODAY) == 10

    def test_mixed_case_country_code(self) -> None:
        stays = [_stay("2026-01-01", "2026-01-05", code="Fr", name="France")]
        assert calculate_schengen_days(stays, TODAY) == 5

    def test_exactly_90_days(self) -> None:
        # 90 days ending exactly on TODAY
        start = TODAY - timedelta(days=89)  # 89-day offset = 90 inclusive days
        stays = [_stay(start.isoformat(), TODAY.isoformat())]
        assert calculate_schengen_days(stays, TODAY) == 90


class TestSchengenStatus:
    def test_under_cap_no_next_free_date(self) -> None:
        stays = [_stay("2026-01-01", "2026-01-10")]
        result = schengen_status(stays, TODAY)
        assert result.days_used == 10
        assert result.days_remaining == 80
        assert result.next_free_date is None

    def test_at_cap_provides_next_free_date(self) -> None:
        # 90 days starting from TODAY - 89 days
        start = TODAY - timedelta(days=89)
        stays = [_stay(start.isoformat(), TODAY.isoformat())]
        result = schengen_status(stays, TODAY)
        assert result.days_used == 90
        assert result.days_remaining == 0
        assert result.next_free_date is not None
        assert result.next_free_date > TODAY

    def test_over_cap_clamped_to_zero_remaining(self) -> None:
        # Two overlapping windows worth of stays (theoretically > 90 days used)
        stays = [
            _stay("2026-01-01", "2026-03-31", code="FR", name="France"),  # 90 days
            _stay("2026-04-01", "2026-04-30", code="DE", name="Germany"),  # 30 more
        ]
        result = schengen_status(stays, TODAY)
        assert result.days_remaining == 0
        assert result.days_used > 90

    def test_no_schengen_stays(self) -> None:
        stays = [_stay("2026-01-01", "2026-01-10", code="TH", name="Thailand")]
        result = schengen_status(stays, TODAY)
        assert result.days_used == 0
        assert result.days_remaining == 90
        assert result.next_free_date is None

    def test_empty_stays(self) -> None:
        result = schengen_status([], TODAY)
        assert result == SchengenResult(
            days_used=0, days_remaining=90, next_free_date=None
        )

    def test_active_stay_at_exact_90_day_cap(self) -> None:
        # Active stay that has been going for exactly 90 days
        start = TODAY - timedelta(days=89)
        stays = [_stay(start.isoformat(), code="FR", name="France")]
        result = schengen_status(stays, TODAY)
        assert result.days_used == 90
        assert result.days_remaining == 0
        assert result.next_free_date is not None

    def test_next_free_date_is_day_after_oldest_day_rolls_off(self) -> None:
        # Stay of exactly 90 days anchored at WINDOW_START (the oldest possible day).
        # When the window advances by 1 day, WINDOW_START rolls off → 89 days → free.
        stay_end = WINDOW_START + timedelta(days=89)  # 90 inclusive days
        stays = [_stay(WINDOW_START.isoformat(), stay_end.isoformat())]
        result = schengen_status(stays, TODAY)
        assert result.days_used == 90
        assert result.next_free_date == TODAY + timedelta(days=1)

    def test_multiple_countries_combined_exceed_cap(self) -> None:
        # France 60 days + Germany 40 days = 100 combined days, 10 over cap.
        fr_end = WINDOW_START + timedelta(days=59)  # 60 inclusive France days
        de_start = fr_end + timedelta(days=1)
        de_end = de_start + timedelta(days=39)  # 40 inclusive Germany days
        stays = [
            _stay(
                WINDOW_START.isoformat(), fr_end.isoformat(), code="FR", name="France"
            ),
            _stay(de_start.isoformat(), de_end.isoformat(), code="DE", name="Germany"),
        ]
        result = schengen_status(stays, TODAY)
        assert result.days_used == 100
        assert result.days_remaining == 0
        assert result.next_free_date is not None

    def test_old_stay_rolls_off_outside_window(self) -> None:
        # Stay entirely before the 180-day window
        stays = [_stay("2025-01-01", "2025-06-01", code="FR", name="France")]
        result = schengen_status(stays, TODAY)
        assert result.days_used == 0

    def test_stay_spanning_window_boundary(self) -> None:
        # Stay begins before window_start and ends well inside it
        stays = [_stay("2025-12-01", "2026-01-10", code="FR", name="France")]
        # Only 2025-12-24 to 2026-01-10 counted = (date(2026,1,10) - date(2025,12,24)).days + 1
        expected = (date(2026, 1, 10) - WINDOW_START).days + 1
        result = schengen_status(stays, TODAY)
        assert result.days_used == expected


class TestNextFreeDate:
    def test_already_under_cap_returns_none(self) -> None:
        stays = [_stay("2026-01-01", "2026-01-10")]
        assert _next_free_date(stays, TODAY) is None

    def test_exactly_at_cap_finds_first_free_day(self) -> None:
        # 90-day stay anchored at WINDOW_START — when window advances 1 day, that day rolls off.
        stay_end = WINDOW_START + timedelta(days=89)  # 90 inclusive days
        stays = [_stay(WINDOW_START.isoformat(), stay_end.isoformat())]
        free = _next_free_date(stays, TODAY)
        assert free == TODAY + timedelta(days=1)

    def test_no_stays_returns_none(self) -> None:
        assert _next_free_date([], TODAY) is None

    def test_active_stay_capped_at_as_of_for_future_calc(self) -> None:
        # An open stay (no exit) must give the same result as a closed stay ending at as_of.
        # This verifies future days are not projected forward in the sliding-window calc.
        open_stays = [_stay(WINDOW_START.isoformat(), code="FR", name="France")]
        closed_stays = [
            _stay(WINDOW_START.isoformat(), TODAY.isoformat(), code="FR", name="France")
        ]
        open_free = _next_free_date(open_stays, TODAY)
        closed_free = _next_free_date(closed_stays, TODAY)
        assert open_free == closed_free
