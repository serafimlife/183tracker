"""Format residency stats for Telegram messages (uses pure engine)."""

from dataclasses import dataclass
from datetime import date

from app.models.stay import Stay
from app.residency_engine import (
    StayRecord,
    calculate_calendar_year_days,
    calculate_remaining_days,
    calculate_rolling_365_days,
    stay_duration_days,
)
from app.utils.countries import flag_emoji


def stay_to_record(stay: Stay) -> StayRecord:
    return StayRecord(
        entry_date=stay.entry_date,
        exit_date=stay.exit_date,
        country_code=stay.country_code,
        country_name=stay.country_name,
        stay_id=stay.id,
    )


def stays_to_records(stays: list[Stay]) -> list[StayRecord]:
    return [stay_to_record(s) for s in stays]


@dataclass(frozen=True, slots=True)
class CountryResidencyStats:
    current_stay_days: int | None
    calendar_year_days: int
    rolling_365_days: int
    remaining_days: int
    year: int


class ResidencyService:
    @staticmethod
    def stats_for_country(
        stays: list[Stay],
        country_code: str,
        *,
        as_of: date | None = None,
        active_stay: Stay | None = None,
    ) -> CountryResidencyStats:
        reference = as_of or date.today()
        records = stays_to_records(stays)
        year = reference.year

        current: int | None = None
        if active_stay is not None and active_stay.country_code == country_code:
            current = stay_duration_days(
                active_stay.entry_date,
                active_stay.exit_date,
                as_of=reference,
            )

        calendar = calculate_calendar_year_days(
            records, year, country_code=country_code, as_of=reference
        )
        rolling = calculate_rolling_365_days(
            records, reference, country_code=country_code
        )
        remaining = calculate_remaining_days(calendar)

        return CountryResidencyStats(
            current_stay_days=current,
            calendar_year_days=calendar,
            rolling_365_days=rolling,
            remaining_days=remaining,
            year=year,
        )

    @staticmethod
    def format_stay_period(
        stay: Stay | StayRecord,
        *,
        date_format: str | None,
        present_label: str = "Present",
    ) -> str:
        record = stay if isinstance(stay, StayRecord) else stay_to_record(stay)
        flag = flag_emoji(record.country_code)
        start = _format_display_date(record.entry_date, date_format)
        if record.exit_date is None:
            return f"{flag} {record.country_name}\n{start} → {present_label}"
        end = _format_display_date(record.exit_date, date_format)
        return f"{flag} {record.country_name}\n{start} → {end}"

    @staticmethod
    def format_stay_range_compact(
        stay: Stay | StayRecord,
        *,
        date_format: str | None,
        present_label: str = "Present",
    ) -> str:
        """Compact range for inline button labels (e.g. 17.05.26–Present)."""
        record = stay if isinstance(stay, StayRecord) else stay_to_record(stay)
        start = _format_compact_date(record.entry_date, date_format)
        if record.exit_date is None:
            end = present_label
        else:
            end = _format_compact_date(record.exit_date, date_format)
        return f"{start}–{end}"


def _format_display_date(value: date, date_format: str | None) -> str:
    """Human-readable date for messages (e.g. 25 February 2026)."""
    if date_format == "mdy":
        return f"{value.strftime('%B')} {value.day}, {value.year}"
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _format_compact_date(value: date, date_format: str | None) -> str:
    if date_format == "mdy":
        return value.strftime("%m.%d.%y")
    return value.strftime("%d.%m.%y")
