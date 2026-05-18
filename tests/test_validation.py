"""Tests for stay overlap validation."""

from datetime import date

from app.residency_engine.types import StayRecord
from app.residency_engine.validation import find_overlapping_stay


def _stay(
    entry: str,
    exit: str | None,
    code: str,
    name: str,
    stay_id: int,
) -> StayRecord:
    return StayRecord(
        date.fromisoformat(entry),
        date.fromisoformat(exit) if exit else None,
        code,
        name,
        stay_id,
    )


def test_same_day_country_transfer_allowed() -> None:
    stays = [
        _stay("2026-01-01", "2026-01-30", "ID", "Indonesia", 1),
    ]
    conflict = find_overlapping_stay(
        stays,
        date(2026, 1, 30),
        date(2026, 2, 10),
        as_of=date(2026, 12, 31),
    )
    assert conflict is None


def test_invalid_overlap_detected() -> None:
    stays = [
        _stay("2026-01-01", "2026-01-30", "ID", "Indonesia", 1),
    ]
    conflict = find_overlapping_stay(
        stays,
        date(2026, 1, 29),
        date(2026, 2, 10),
        as_of=date(2026, 12, 31),
    )
    assert conflict is not None
    assert conflict.country_code == "ID"


def test_open_entry_overlap() -> None:
    stays = [
        _stay("2026-01-01", "2026-01-30", "ID", "Indonesia", 1),
    ]
    conflict = find_overlapping_stay(
        stays,
        date(2026, 1, 15),
        None,
        as_of=date(2026, 12, 31),
    )
    assert conflict is not None


def test_exclude_self_on_close() -> None:
    stays = [
        _stay("2026-01-01", None, "TH", "Thailand", 1),
    ]
    conflict = find_overlapping_stay(
        stays,
        date(2026, 1, 1),
        date(2026, 1, 30),
        exclude_stay_id=1,
        as_of=date(2026, 12, 31),
    )
    assert conflict is None
