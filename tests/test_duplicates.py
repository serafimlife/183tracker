"""Tests for duplicate stay detection."""

from datetime import date

from app.residency_engine.duplicates import find_duplicate_entry, find_duplicate_exit
from app.residency_engine.types import StayRecord


def _stay(
    entry: str,
    exit: str | None,
    code: str = "TH",
    stay_id: int = 1,
) -> StayRecord:
    return StayRecord(
        date.fromisoformat(entry),
        date.fromisoformat(exit) if exit else None,
        code,
        "Thailand",
        stay_id,
    )


def test_find_duplicate_entry() -> None:
    stays = [_stay("2026-05-17", None)]
    assert find_duplicate_entry(stays, "TH", date(2026, 5, 17)) is not None


def test_find_duplicate_entry_no_match() -> None:
    stays = [_stay("2026-05-17", None)]
    assert find_duplicate_entry(stays, "TH", date(2026, 5, 18)) is None


def test_find_duplicate_exit() -> None:
    stays = [_stay("2026-01-01", "2026-08-30")]
    assert find_duplicate_exit(stays, "TH", date(2026, 8, 30)) is not None


def test_find_duplicate_exit_open_stay_ignored() -> None:
    stays = [_stay("2026-05-17", None)]
    assert find_duplicate_exit(stays, "TH", date(2026, 5, 17)) is None
