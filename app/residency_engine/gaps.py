"""Untracked gap detection between consecutive stays."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.residency_engine.types import StayRecord


@dataclass(frozen=True, slots=True)
class UntrackedGap:
    """Gap of more than 3 days between a prior stay exit and a new entry."""

    prior: StayRecord
    gap_start: date
    gap_end: date
    gap_days: int


def find_untracked_gap(
    stays: Sequence[StayRecord],
    new_entry: date,
) -> UntrackedGap | None:
    """Detect advisory gap before `new_entry` (same-day transfers excluded)."""
    closed = [s for s in stays if s.exit_date is not None and s.exit_date <= new_entry]
    if not closed:
        return None

    prior = max(closed, key=lambda s: s.exit_date)  # type: ignore[arg-type, return-value]
    assert prior.exit_date is not None

    gap_days = (new_entry - prior.exit_date).days - 1
    if gap_days <= 3:
        return None

    gap_start = prior.exit_date + timedelta(days=1)
    gap_end = new_entry - timedelta(days=1)
    return UntrackedGap(
        prior=prior,
        gap_start=gap_start,
        gap_end=gap_end,
        gap_days=gap_days,
    )
