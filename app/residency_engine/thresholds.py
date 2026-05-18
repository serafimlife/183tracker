"""183-day threshold helpers."""


def calculate_remaining_days(days_spent: int, threshold: int = 183) -> int:
    """Days remaining before reaching `threshold` (never negative)."""
    return max(0, threshold - days_spent)
