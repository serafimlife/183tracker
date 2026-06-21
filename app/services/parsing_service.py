"""Parse Telegram command text into structured arguments."""

from dataclasses import dataclass
from datetime import date

from app.utils.dates import parse_entry_date
from app.services.filters import TimelineFilter, parse_timeline_filter, _parse_year


@dataclass(frozen=True, slots=True)
class ParsedCountryCommand:
    country_input: str
    date_str: str


ParsedInCommand = ParsedCountryCommand
ParsedOutCommand = ParsedCountryCommand


@dataclass(frozen=True, slots=True)
class ParsedLogCommand:
    country_input: str
    entry_date_str: str
    exit_date_str: str


@dataclass(frozen=True, slots=True)
class ParsedHistoryCommand:
    country_input: str | None = None
    year: int | None = None
    start_date: date | None = None
    end_date: date | None = None
    current_year: bool = False


class ParsingService:
    """Extract country and date from `/in` messages."""

    @staticmethod
    def extract_in_command_body(text: str) -> str | None:
        body = text.strip()
        if body.lower().startswith("/in"):
            return body[3:].strip()
        if body.lower().startswith("in"):
            return body[2:].strip()
        return None

    @staticmethod
    def parse_in_command(text: str) -> ParsedInCommand | None:
        """Parse `/in Country date` (country may contain spaces)."""
        body = ParsingService.extract_in_command_body(text)
        if body is None:
            return None

        parts = body.split()
        if len(parts) < 2:
            return None

        date_str = parts[-1]
        country_input = " ".join(parts[:-1])
        if not country_input:
            return None

        return ParsedCountryCommand(country_input=country_input, date_str=date_str)

    @staticmethod
    def parse_out_command(text: str) -> ParsedOutCommand | None:
        """Parse `/out Country date` (country may contain spaces)."""
        body = ParsingService.extract_out_command_body(text)
        if body is None:
            return None

        parts = body.split()
        if len(parts) < 2:
            return None

        date_str = parts[-1]
        country_input = " ".join(parts[:-1])
        if not country_input:
            return None

        return ParsedCountryCommand(country_input=country_input, date_str=date_str)

    @staticmethod
    def extract_out_command_body(text: str) -> str | None:
        body = text.strip()
        if body.lower().startswith("/out"):
            return body[4:].strip()
        if body.lower().startswith("out"):
            return body[3:].strip()
        return None

    @staticmethod
    def extract_log_command_body(text: str) -> str | None:
        body = text.strip()
        if body.lower().startswith("/log"):
            return body[4:].strip()
        if body.lower().startswith("log"):
            return body[3:].strip()
        return None

    @staticmethod
    def parse_log_command(text: str) -> ParsedLogCommand | None:
        """Parse `/log Country entry-date exit-date`."""
        body = ParsingService.extract_log_command_body(text)
        if body is None:
            return None

        parts = body.split()
        if len(parts) < 3:
            return None

        country_input = " ".join(parts[:-2])
        if not country_input:
            return None

        return ParsedLogCommand(
            country_input=country_input,
            entry_date_str=parts[-2],
            exit_date_str=parts[-1],
        )

    @staticmethod
    def parse_history_command(
        text: str,
        *,
        date_format: str | None,
        today: date | None = None,
    ) -> ParsedHistoryCommand | None:
        body = text.strip()
        lowered = body.lower()
        if lowered.startswith("/history"):
            body = body[8:].strip()
        elif lowered.startswith("history"):
            body = body[7:].strip()
        else:
            return None

        result = parse_timeline_filter(body, date_format=date_format, today=today)
        if result is None:
            return None
        return ParsedHistoryCommand(
            country_input=result.country_input,
            year=result.year,
            start_date=result.start_date,
            end_date=result.end_date,
            current_year=result.current_year,
        )

    @staticmethod
    def parse_history_date_range(
        text: str,
        *,
        date_format: str | None,
        today: date | None = None,
    ) -> ParsedHistoryCommand | None:
        parts = text.strip().split()
        if len(parts) != 2:
            return None
        reference = today or date.today()
        start = parse_entry_date(parts[0], date_format=date_format, today=reference)
        end = parse_entry_date(parts[1], date_format=date_format, today=reference)
        if start is None or end is None or end < start:
            return None
        return ParsedHistoryCommand(start_date=start, end_date=end)
