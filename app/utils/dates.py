"""Date parsing helpers for user commands."""

from datetime import date, datetime

from app.utils.onboarding import DateFormat


def parse_entry_date(
    date_str: str,
    *,
    date_format: str | None,
    today: date | None = None,
) -> date | None:
    """Parse a date token from /in or /out (supports `today` and user format)."""
    token = date_str.strip().lower()
    if token == "today":
        return today or date.today()

    fmt = date_format or DateFormat.DMY.value
    patterns = (
        ["%d.%m.%y", "%d.%m.%Y"] if fmt == DateFormat.DMY.value else ["%m.%d.%y", "%m.%d.%Y"]
    )
    for pattern in patterns:
        try:
            return datetime.strptime(date_str.strip(), pattern).date()
        except ValueError:
            continue
    return None
