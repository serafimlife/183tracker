"""Date parsing helpers for user commands."""

from datetime import date, datetime, timedelta

from app.utils.onboarding import DateFormat


def parse_entry_date(
    date_str: str,
    *,
    date_format: str | None,
    today: date | None = None,
) -> date | None:
    """Parse a date token from /in or /out (supports `today` and user format)."""
    token = date_str.strip().lower()
    reference = today or date.today()
    if token == "today":
        return reference
    if token == "yesterday":
        return reference - timedelta(days=1)

    fmt = date_format or DateFormat.DMY.value
    separators = (".", "-", "/")
    patterns = []
    for separator in separators:
        if fmt == DateFormat.DMY.value:
            patterns.extend(
                [f"%d{separator}%m{separator}%y", f"%d{separator}%m{separator}%Y"]
            )
        else:
            patterns.extend(
                [f"%m{separator}%d{separator}%y", f"%m{separator}%d{separator}%Y"]
            )
    for pattern in patterns:
        try:
            return datetime.strptime(date_str.strip(), pattern).date()
        except ValueError:
            continue
    return None
