"""Tests for /help command."""

import pytest
from unittest.mock import AsyncMock

from app.handlers.help import HELP_TEXT, cmd_help


def test_help_text_contains_all_commands() -> None:
    assert "/in" in HELP_TEXT
    assert "/out" in HELP_TEXT
    assert "/log" in HELP_TEXT
    assert "/where" in HELP_TEXT
    assert "/history" in HELP_TEXT
    assert "/report" in HELP_TEXT
    assert "/settings" in HELP_TEXT


def test_help_text_contains_sections() -> None:
    assert "TRAVEL" in HELP_TEXT
    assert "STATUS" in HELP_TEXT
    assert "HISTORY" in HELP_TEXT
    assert "REPORTS" in HELP_TEXT
    assert "SETTINGS" in HELP_TEXT


def test_help_text_shows_examples() -> None:
    assert "Thailand" in HELP_TEXT
    assert "today" in HELP_TEXT
    assert "01.01.2026" in HELP_TEXT


def test_help_text_exact_header() -> None:
    assert HELP_TEXT.startswith("🏝 Residency Tracker")


@pytest.mark.asyncio
async def test_cmd_help_sends_help_text() -> None:
    message = AsyncMock()
    await cmd_help(message)
    message.answer.assert_awaited_once_with(HELP_TEXT)
