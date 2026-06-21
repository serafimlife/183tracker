"""Residency aggregation for /report."""

from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.report import ReportFilterCallback
from app.models.stay import Stay
from app.models.user import User
from app.repositories.stay_repository import StayRepository
from app.residency_engine import (
    SCHENGEN_CODES,
    calculate_remaining_days,
    calculate_rolling_365_days,
    schengen_status,
    stay_duration_days,
)
from app.residency_engine.intervals import days_in_range_within
from app.residency_engine.types import StayRecord
from app.services.filters import TimelineFilter
from app.services.parsing_service import ParsingService
from app.services.localization_service import LocalizationService
from app.services.history_service import MessageResult
from app.utils.countries import flag_emoji, resolve_country
from app.utils.formatters import format_duration_days, get_threshold_indicator
from app.utils.onboarding import DateFormat


class ReportService:
    """Aggregate residency days by country for /report."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = StayRepository(session)

    async def handle_report_command(
        self,
        user: User,
        filter: TimelineFilter,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")

        country_code: str | None = None
        country_name: str | None = None
        if filter.country_input is not None:
            country = resolve_country(filter.country_input)
            if country is None:
                return MessageResult(message=i18n.t("in.country_not_recognized"))
            country_code = country["code"]
            country_name = country["name"]

        keyboard = self._report_keyboard(i18n, filter)
        window = _report_window(filter)
        has_explicit_dates = filter.start_date is not None and filter.end_date is not None
        stays = await self._repo.list_by_user(user.telegram_id)

        as_of = date.today()
        totals: dict[str, int] = {}
        names: dict[str, str] = {}
        all_records: list[StayRecord] = []
        records_by_code: dict[str, list[StayRecord]] = {}
        min_entry_by_code: dict[str, date] = {}

        for stay in stays:
            record = StayRecord(
                entry_date=stay.entry_date,
                exit_date=stay.exit_date,
                country_code=stay.country_code,
                country_name=stay.country_name,
                stay_id=stay.id,
            )
            all_records.append(record)

            if country_code is not None and stay.country_code != country_code:
                continue

            days = _report_duration_days(stay, window)
            code = stay.country_code

            if days > 0:
                totals[code] = totals.get(code, 0) + days
                names[code] = stay.country_name

            # Collect ALL records for rolling 365 calculation,
            # not just those in the selected window.
            records_by_code.setdefault(code, []).append(record)

            # Track earliest entry for all-time period header
            if code not in min_entry_by_code or stay.entry_date < min_entry_by_code[code]:
                min_entry_by_code[code] = stay.entry_date

        if not totals:
            return MessageResult(message=i18n.t("report.empty"), keyboard=keyboard)

        sorted_codes = sorted(totals, key=totals.get, reverse=True)

        # For all-time country view (no year, no explicit dates), show period bounds in header
        period_start: date | None = None
        period_end: date | None = None
        if window is None and not has_explicit_dates and sorted_codes:
            period_start = min(
                min_entry_by_code.get(c, as_of) for c in sorted_codes
            )
            period_end = as_of

        header = _report_header(
            i18n, filter, country_name, date_format=user.date_format,
            period_start=period_start, period_end=period_end,
        )
        lines: list[str] = []
        for code in sorted_codes:
            period = totals[code]
            rolling = calculate_rolling_365_days(
                records_by_code[code], as_of, country_code=code
            )
            roll_remaining = calculate_remaining_days(rolling)

            lines.append(
                i18n.t(
                    "report.country_header", flag=flag_emoji(code), country=names[code]
                )
            )
            lines.append(
                i18n.t("report.period_days", days=format_duration_days(period, i18n))
            )
            lines.append(
                i18n.t("report.rolling_days", days=format_duration_days(rolling, i18n))
            )
            lines.append("")
            # Calendar threshold only makes sense for a year-scoped view
            if not has_explicit_dates and window is not None:
                cal_remaining = calculate_remaining_days(period)
                lines.append(
                    i18n.t(
                        "report.threshold_calendar",
                        indicator=get_threshold_indicator(cal_remaining),
                        days=format_duration_days(cal_remaining, i18n),
                    )
                )
            lines.append(
                i18n.t(
                    "report.threshold_rolling",
                    indicator=get_threshold_indicator(roll_remaining),
                    days=format_duration_days(roll_remaining, i18n),
                )
            )
            lines.append("")

        schengen_result = schengen_status(all_records, as_of)
        show_schengen = schengen_result.days_used > 0 and (
            country_code is None or country_code.upper() in SCHENGEN_CODES
        )

        if show_schengen:
            lines.append(i18n.t("schengen.header"))
            lines.append(
                i18n.t(
                    "schengen.days_used",
                    days=format_duration_days(schengen_result.days_used, i18n),
                )
            )
            lines.append(
                i18n.t(
                    "schengen.days_remaining",
                    indicator=get_threshold_indicator(schengen_result.days_remaining),
                    days=format_duration_days(schengen_result.days_remaining, i18n),
                )
            )
            if schengen_result.next_free_date is not None:
                lines.append(
                    i18n.t(
                        "schengen.next_free_date",
                        date=_format_report_date(
                            schengen_result.next_free_date, user.date_format
                        ),
                    )
                )
            lines.append("")

        message = header + "\n\n" + "\n".join(lines).rstrip("\n")
        return MessageResult(message=message, keyboard=keyboard)

    async def handle_report_callback(
        self, user: User, filter_key: str
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        base_filter_key = _custom_base_filter_key(filter_key)
        if base_filter_key is not None:
            return MessageResult(
                message=i18n.t("history.custom_dates_prompt"),
                fsm_data={"report_base_filter_key": base_filter_key},
            )

        filter = _filter_from_key(filter_key)
        if filter is None:
            return MessageResult(message=i18n.t("history.invalid_usage"))
        return await self.handle_report_command(user, filter)

    async def handle_custom_date_range(
        self,
        user: User,
        text: str,
        *,
        base_filter_key: str | None = None,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        parsed = ParsingService.parse_history_date_range(
            text,
            date_format=user.date_format,
        )
        if parsed is None:
            return MessageResult(message=i18n.t("history.custom_dates_error"))

        filter = TimelineFilter(start_date=parsed.start_date, end_date=parsed.end_date)
        if base_filter_key is not None:
            base = _filter_from_key(base_filter_key)
            if base is None:
                return MessageResult(message=i18n.t("history.invalid_usage"))
            filter = TimelineFilter(
                country_input=base.country_input,
                year=base.year,
                start_date=parsed.start_date,
                end_date=parsed.end_date,
            )
        return await self.handle_report_command(user, filter)

    def cancel_custom_dates(self, user: User) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        return MessageResult(message=i18n.t("history.custom_dates_cancelled"))

    def _report_keyboard(
        self,
        i18n: LocalizationService,
        filter: TimelineFilter,
    ) -> InlineKeyboardMarkup:
        current_year = date.today().year
        base_key = _filter_key(filter)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    _filter_button(str(current_year), f"y{current_year}"),
                    _filter_button(str(current_year - 1), f"y{current_year - 1}"),
                    _filter_button(str(current_year - 2), f"y{current_year - 2}"),
                ],
                [
                    _filter_button(
                        i18n.t("history.custom_dates_button"),
                        _custom_filter_key(base_key),
                    )
                ],
            ]
        )


def _report_window(filter: TimelineFilter) -> tuple[date, date] | None:
    """Compute (start, end) window from a TimelineFilter."""
    if filter.start_date is not None and filter.end_date is not None:
        return (filter.start_date, filter.end_date)
    if filter.year is not None:
        return (date(filter.year, 1, 1), date(filter.year, 12, 31))
    return None


def _report_duration_days(
    stay: Stay,
    window: tuple[date, date] | None,
) -> int:
    """Overlap-aware day count for a stay within an optional window.

    Active stays (exit=None) are always capped to today so future
    days are never counted.
    """
    as_of = date.today()
    if window is None:
        return stay_duration_days(stay.entry_date, stay.exit_date, as_of=as_of)
    return days_in_range_within(
        stay.entry_date,
        stay.exit_date,
        window,
        cap=min(window[1], as_of) if stay.exit_date is None else window[1],
    )


def _report_header(
    i18n: LocalizationService,
    filter: TimelineFilter,
    country_name: str | None,
    *,
    date_format: str | None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> str:
    """Build the report header with optional filter labels."""
    if filter.start_date is not None and filter.end_date is not None:
        range_label = (
            f"{_format_report_date(filter.start_date, date_format)}"
            f"–{_format_report_date(filter.end_date, date_format)}"
        )
        if country_name is not None:
            return (
                i18n.t("report.title_country", country=country_name)
                + f" — {range_label}"
            )
        return i18n.t("report.title") + f" — {range_label}"
    if country_name is not None and filter.year is not None:
        return i18n.t(
            "report.title_country_year", country=country_name, year=filter.year
        )
    if country_name is not None and period_start is not None and period_end is not None:
        range_label = (
            f"{_format_report_date(period_start, date_format)}"
            f"–{_format_report_date(period_end, date_format)}"
        )
        return i18n.t("report.title_country", country=country_name) + f" — {range_label}"
    if country_name is not None:
        return i18n.t("report.title_country", country=country_name)
    if filter.year is not None:
        return i18n.t("report.title_year", year=filter.year)
    return i18n.t("report.title")


def _format_report_date(value: date, date_format: str | None) -> str:
    fmt = DateFormat(date_format or DateFormat.DMY.value)
    if fmt == DateFormat.MDY:
        return value.strftime("%b %-d %Y")
    return value.strftime("%-d %b %Y")


def _filter_button(text: str, filter_key: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=ReportFilterCallback(filter_key=filter_key).pack(),
    )


def _filter_key(filter: TimelineFilter) -> str:
    if filter.country_input is not None and filter.year is not None:
        country = resolve_country(filter.country_input)
        code = country["code"] if country is not None else filter.country_input
        return f"cy{code}-{filter.year}"
    if filter.country_input is not None:
        country = resolve_country(filter.country_input)
        code = country["code"] if country is not None else filter.country_input
        return f"c{code}"
    if filter.year is not None:
        return f"y{filter.year}"
    return f"y{date.today().year}"


def _custom_filter_key(base_key: str) -> str:
    return f"custom_{base_key}"


def _custom_base_filter_key(filter_key: str) -> str | None:
    if not filter_key.startswith("custom_"):
        return None
    base = filter_key[7:]
    return base or None


def _filter_from_key(filter_key: str) -> TimelineFilter | None:
    if filter_key.startswith("y") and filter_key[1:].isdigit():
        return TimelineFilter(year=int(filter_key[1:]))
    if filter_key.startswith("c") and not filter_key.startswith("cy"):
        return TimelineFilter(country_input=filter_key[1:])
    if filter_key.startswith("cy"):
        rest = filter_key[2:]
        if "-" not in rest:
            return None
        code, year = rest.split("-", 1)
        if not code or not year.isdigit():
            return None
        return TimelineFilter(country_input=code, year=int(year))
    return None
