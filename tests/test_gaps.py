"""Tests for untracked gap detection."""

from datetime import date

from app.residency_engine.gaps import find_untracked_gap
from app.residency_engine.types import StayRecord


def _stay(entry: str, exit: str, code: str, name: str) -> StayRecord:
    return StayRecord(
        date.fromisoformat(entry),
        date.fromisoformat(exit),
        code,
        name,
    )


def test_no_gap_when_first_stay() -> None:
    assert find_untracked_gap([], date(2026, 6, 20)) is None


def test_same_day_transfer_no_gap() -> None:
    stays = [_stay("2026-01-01", "2026-06-10", "ID", "Indonesia")]
    assert find_untracked_gap(stays, date(2026, 6, 10)) is None


def test_one_day_gap_no_warning() -> None:
    stays = [_stay("2026-01-01", "2026-06-10", "ID", "Indonesia")]
    assert find_untracked_gap(stays, date(2026, 6, 12)) is None


def test_three_day_gap_no_warning() -> None:
    stays = [_stay("2026-01-01", "2026-06-10", "ID", "Indonesia")]
    # gap 11,12,13 = 3 days
    assert find_untracked_gap(stays, date(2026, 6, 14)) is None


def test_four_day_gap_triggers() -> None:
    stays = [_stay("2026-01-01", "2026-06-10", "ID", "Indonesia")]
    gap = find_untracked_gap(stays, date(2026, 6, 15))
    assert gap is not None
    assert gap.gap_days == 4
    assert gap.gap_start == date(2026, 6, 11)
    assert gap.gap_end == date(2026, 6, 14)


def test_nine_day_gap_example() -> None:
    stays = [_stay("2026-01-01", "2026-06-10", "ID", "Indonesia")]
    gap = find_untracked_gap(stays, date(2026, 6, 20))
    assert gap is not None
    assert gap.gap_days == 9
    assert gap.gap_start == date(2026, 6, 11)
    assert gap.gap_end == date(2026, 6, 19)
