"""Tests for threshold calculations."""

from app.residency_engine.thresholds import calculate_remaining_days


def test_remaining_days() -> None:
    assert calculate_remaining_days(82) == 101
    assert calculate_remaining_days(183) == 0
    assert calculate_remaining_days(200) == 0
