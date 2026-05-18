"""Tests for country resolution."""

import pytest

from app.utils.countries import flag_emoji, resolve_country


@pytest.mark.parametrize(
    ("user_input", "code", "name"),
    [
        ("Thailand", "TH", "Thailand"),
        ("thailand", "TH", "Thailand"),
        ("  Indonesia  ", "ID", "Indonesia"),
        ("USA", "US", "United States"),
        ("US", "US", "United States"),
        ("UK", "GB", "United Kingdom"),
        ("UAE", "AE", "United Arab Emirates"),
        ("South Korea", "KR", "Korea, Republic of"),
        ("North Korea", "KP", "Korea, Democratic People's Republic of"),
        ("Russia", "RU", "Russian Federation"),
        ("ID", "ID", "Indonesia"),
    ],
)
def test_resolve_country(user_input: str, code: str, name: str) -> None:
    result = resolve_country(user_input)
    assert result is not None
    assert result["code"] == code
    assert result["name"] == name
    assert result["flag"] == flag_emoji(code)


def test_resolve_country_invalid() -> None:
    assert resolve_country("Atlantis") is None
    assert resolve_country("") is None


def test_flag_emoji_generated() -> None:
    assert flag_emoji("TH") == "🇹🇭"
    assert flag_emoji("th") == "🇹🇭"
