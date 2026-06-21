"""Shared user-facing formatting helpers."""

from typing import Any


def format_duration_days(days: int, i18n: Any | None = None) -> str:
    """Format a day count with localized singular/plural labels."""
    count = max(0, days)
    if i18n is None:
        unit = "day" if count == 1 else "days"
        return f"{count} {unit}"
    key = "duration.day" if count == 1 else "duration.days"
    return i18n.t(key, days=count)


def get_threshold_indicator(remaining_days: int) -> str:
    """Return an emoji indicator based on how many days remain before a threshold.

    Rules:
      - 🟢 if remaining > 60
      - 🟡 if remaining 31-60
      - 🔴 if remaining <= 30
    """
    if remaining_days > 60:
        return "\U0001f7e2"
    if remaining_days >= 31:
        return "\U0001f7e1"
    return "\U0001f534"
