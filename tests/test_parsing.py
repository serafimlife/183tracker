"""Tests for command parsing."""

from datetime import date

from app.utils.dates import parse_entry_date
from app.services.parsing_service import ParsingService


def test_parse_in_command() -> None:
    parsed = ParsingService.parse_in_command("/in Thailand today")
    assert parsed is not None
    assert parsed.country_input == "Thailand"
    assert parsed.date_str == "today"


def test_parse_in_command_multipart_country() -> None:
    parsed = ParsingService.parse_in_command("/in United States 07.26.26")
    assert parsed is not None
    assert parsed.country_input == "United States"
    assert parsed.date_str == "07.26.26"


def test_parse_in_command_invalid() -> None:
    assert ParsingService.parse_in_command("/in Thailand") is None


def test_extract_in_command_body() -> None:
    assert (
        ParsingService.extract_in_command_body("/in Thailand today") == "Thailand today"
    )
    assert ParsingService.extract_in_command_body("/in") == ""


def test_extract_out_command_body() -> None:
    assert (
        ParsingService.extract_out_command_body("/out Thailand today")
        == "Thailand today"
    )
    assert ParsingService.extract_out_command_body("/out") == ""


def test_parse_log_command_multipart_country() -> None:
    parsed = ParsingService.parse_log_command("/log United States 01.01.26 15.01.26")
    assert parsed is not None
    assert parsed.country_input == "United States"
    assert parsed.entry_date_str == "01.01.26"
    assert parsed.exit_date_str == "15.01.26"


def test_parse_entry_date_yesterday() -> None:
    assert parse_entry_date(
        "yesterday", date_format="dmy", today=date(2026, 5, 25)
    ) == date(2026, 5, 24)
