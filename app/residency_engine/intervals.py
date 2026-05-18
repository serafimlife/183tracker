"""Date interval utilities — inclusive ranges, overlap, merge."""

from datetime import date, timedelta

# Inclusive date range: both endpoints count as full days.
DateRange = tuple[date, date]

OPEN_END = date.max


def inclusive_days(start: date, end: date) -> int:
    """Count days in [start, end] inclusive."""
    return (end - start).days + 1


def effective_end(exit_date: date | None, *, cap: date | None = None) -> date:
    """Resolve open-ended stays; optional cap (e.g. today or year-end)."""
    if exit_date is None:
        end = OPEN_END if cap is None else cap
    else:
        end = exit_date
    if cap is not None and end > cap:
        return cap
    return end


def to_range(
    entry_date: date,
    exit_date: date | None,
    *,
    cap: date | None = None,
) -> DateRange:
    return (entry_date, effective_end(exit_date, cap=cap))


def intersect_ranges(a: DateRange, b: DateRange) -> DateRange | None:
    """Return inclusive intersection or None if disjoint."""
    start = max(a[0], b[0])
    end = min(a[1], b[1])
    if start > end:
        return None
    return (start, end)


def count_overlap_days(a: DateRange, b: DateRange) -> int:
    """Inclusive overlap day count between two ranges."""
    intersection = intersect_ranges(a, b)
    if intersection is None:
        return 0
    return inclusive_days(intersection[0], intersection[1])


def has_overlap(
    start_a: date,
    end_a: date | None,
    start_b: date,
    end_b: date | None,
    *,
    cap_a: date | None = None,
    cap_b: date | None = None,
) -> bool:
    """True when intervals overlap beyond same-day boundary touch.

    Touching on one day (A ends 30 Jan, B starts 30 Jan) is NOT overlap:
      start_b < end_a  →  30 < 30  →  False
    """
    a_end = effective_end(end_a, cap=cap_a)
    b_end = effective_end(end_b, cap=cap_b)
    return start_a < b_end and a_end > start_b


def merge_intervals(ranges: list[DateRange]) -> list[DateRange]:
    """Merge overlapping or adjacent inclusive ranges."""
    if not ranges:
        return []

    sorted_ranges = sorted(ranges, key=lambda r: r[0])
    merged: list[DateRange] = [sorted_ranges[0]]

    for start, end in sorted_ranges[1:]:
        prev_start, prev_end = merged[-1]
        # Adjacent: prev ends 30th, next starts 31st → (31 - 30).days == 1
        if start <= prev_end + timedelta(days=1):
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    return merged


def days_in_range_within(
    entry_date: date,
    exit_date: date | None,
    window: DateRange,
    *,
    cap: date | None = None,
) -> int:
    """Inclusive days of a stay that fall inside `window`."""
    stay_range = to_range(entry_date, exit_date, cap=cap)
    intersection = intersect_ranges(stay_range, window)
    if intersection is None:
        return 0
    return inclusive_days(intersection[0], intersection[1])
