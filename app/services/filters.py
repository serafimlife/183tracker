"""Reusable filter infrastructure for timeline queries."""

from dataclasses import dataclass
from datetime import date

from app.utils.dates import parse_entry_date


@dataclass(frozen=True, slots=True)
class TimelineFilter:
    """DTO representing a timeline query filter.

    This is a pure data container with no logic. Country resolution
    happens in the service layer, not in this module.
    """

    country_input: str | None = None
    year: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    current_year: bool = False


def _parse_year(value: str) -> int | None:
    if not value.isdigit() or len(value) != 4:
        return None
    year = int(value)
    if 1900 <= year <= 2100:
        return year
    return None


def parse_timeline_filter(
    body: str,
    *,
    date_format: str | None,
    today: date | None = None,
) -> TimelineFilter | None:
    """Parse a whitespace-separated body into a structured TimelineFilter.

    The body should already be stripped of any command prefix (e.g., '/history').
    This function performs token-level disambiguation for:
      - empty -> current year
      - 'this' -> current year
      - single 4-digit year
      - single word -> country name
      - two dates -> date range
      - name + year
      - name + date range
      - fallback to raw country input
    """
    reference = today or date.today()
    if not body:
        return TimelineFilter(year=reference.year, current_year=True)

    parts = body.split()
    if len(parts) == 1:
        token = parts[0].lower()
        if token == "this":
            return TimelineFilter(year=reference.year, current_year=True)
        year = _parse_year(token)
        if year is not None:
            return TimelineFilter(year=year)
        return TimelineFilter(country_input=parts[0])

    if len(parts) == 2:
        start = parse_entry_date(parts[0], date_format=date_format, today=reference)
        end = parse_entry_date(parts[1], date_format=date_format, today=reference)
        if start is not None and end is not None:
            if end < start:
                return None
            return TimelineFilter(start_date=start, end_date=end)

    # 3+ tokens: last two may be a date range with country prefix
    if len(parts) >= 3:
        start = parse_entry_date(parts[-2], date_format=date_format, today=reference)
        end = parse_entry_date(parts[-1], date_format=date_format, today=reference)
        if start is not None and end is not None:
            if end < start:
                return None
            country_input = " ".join(parts[:-2]).strip()
            if not country_input:
                return None
            return TimelineFilter(
                country_input=country_input, start_date=start, end_date=end
            )

    last_year = _parse_year(parts[-1].lower())
    if last_year is not None:
        country_input = " ".join(parts[:-1]).strip()
        if not country_input:
            return None
        return TimelineFilter(country_input=country_input, year=last_year)

    return TimelineFilter(country_input=body)
