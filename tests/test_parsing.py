"""Tests for command parsing."""

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
