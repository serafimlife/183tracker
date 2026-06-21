"""Tests for date interval utilities."""

from datetime import date

from app.residency_engine.intervals import (
    count_overlap_days,
    has_overlap,
    inclusive_days,
    intersect_ranges,
    merge_intervals,
)


def test_inclusive_days_same_day() -> None:
    assert inclusive_days(date(2026, 3, 1), date(2026, 3, 1)) == 1


def test_inclusive_days_two_days() -> None:
    assert inclusive_days(date(2026, 3, 1), date(2026, 3, 2)) == 2


def test_intersect_ranges_disjoint() -> None:
    assert (
        intersect_ranges(
            (date(2026, 1, 1), date(2026, 1, 10)), (date(2026, 2, 1), date(2026, 2, 10))
        )
        is None
    )


def test_intersect_ranges_overlap() -> None:
    assert intersect_ranges(
        (date(2026, 1, 5), date(2026, 1, 20)), (date(2026, 1, 15), date(2026, 1, 31))
    ) == (
        date(2026, 1, 15),
        date(2026, 1, 20),
    )


def test_count_overlap_days() -> None:
    a = (date(2026, 1, 1), date(2026, 1, 30))
    b = (date(2026, 1, 29), date(2026, 2, 10))
    assert count_overlap_days(a, b) == 2


def test_same_day_transfer_not_overlap() -> None:
    indonesia = (date(2026, 1, 1), date(2026, 1, 30))
    thailand = (date(2026, 1, 30), date(2026, 2, 10))
    assert not has_overlap(indonesia[0], indonesia[1], thailand[0], thailand[1])


def test_invalid_overlap() -> None:
    indonesia = (date(2026, 1, 1), date(2026, 1, 30))
    thailand = (date(2026, 1, 29), date(2026, 2, 10))
    assert has_overlap(indonesia[0], indonesia[1], thailand[0], thailand[1])


def test_open_stay_overlap() -> None:
    assert has_overlap(
        date(2026, 1, 29),
        None,
        date(2026, 1, 1),
        date(2026, 1, 30),
        cap_a=date(2026, 12, 31),
        cap_b=date(2026, 12, 31),
    )


def test_merge_intervals_adjacent() -> None:
    merged = merge_intervals(
        [
            (date(2026, 1, 1), date(2026, 1, 5)),
            (date(2026, 1, 6), date(2026, 1, 10)),
        ]
    )
    assert merged == [(date(2026, 1, 1), date(2026, 1, 10))]
