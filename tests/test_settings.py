"""Tests for /settings handler."""

from unittest.mock import AsyncMock

import pytest

from app.handlers.settings import (
    DELETE_ALL_TRIGGER,
    SettingsDateFormatCallback,
    SettingsMenuCallback,
    _date_format_keyboard,
    _settings_keyboard,
)
from app.services.localization_service import LocalizationService


def test_settings_menu_buttons() -> None:
    i18n = LocalizationService("en")
    keyboard = _settings_keyboard(i18n)
    assert len(keyboard.inline_keyboard) == 4

    assert "Date format:" in keyboard.inline_keyboard[0][0].text
    assert "DD.MM.YY" in keyboard.inline_keyboard[0][0].text
    assert "Import data" in keyboard.inline_keyboard[1][0].text
    assert "Export data" in keyboard.inline_keyboard[2][0].text
    assert "Delete all data" in keyboard.inline_keyboard[3][0].text


def test_settings_menu_callback_data() -> None:
    cb = SettingsMenuCallback(action="date_format")
    unpacked = SettingsMenuCallback.unpack(cb.pack())
    assert unpacked.action == "date_format"

    cb = SettingsMenuCallback(action="back")
    unpacked = SettingsMenuCallback.unpack(cb.pack())
    assert unpacked.action == "back"


def test_delete_all_data_trigger() -> None:
    assert DELETE_ALL_TRIGGER == "DELETE ALL DATA"
    assert DELETE_ALL_TRIGGER != "delete all data"
    assert DELETE_ALL_TRIGGER != "Delete All Data"


@pytest.mark.asyncio
async def test_delete_all_data_nonexistent_user() -> None:
    """Deleting data for a user who doesn't exist should still respond."""
    from app.handlers.settings import on_delete_all_data

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    message = AsyncMock()
    message.from_user.id = 99999

    await on_delete_all_data(message, session)

    session.delete.assert_not_called()
    session.flush.assert_not_called()
    message.answer.assert_called_once()


@pytest.mark.asyncio
async def test_delete_all_data_deletes_user() -> None:
    """Exact trigger should delete the user and respond."""
    from app.handlers.settings import on_delete_all_data

    user = AsyncMock()
    user.language = "en"

    session = AsyncMock()
    session.get = AsyncMock(return_value=user)

    message = AsyncMock()
    message.from_user.id = 100

    await on_delete_all_data(message, session)

    session.delete.assert_called_once_with(user)
    session.flush.assert_called_once()
    message.answer.assert_called_once()


def test_date_format_button_reflects_user_preference_dmy() -> None:
    i18n = LocalizationService("en")
    keyboard = _settings_keyboard(i18n, date_format="dmy")
    assert "DD.MM.YY" in keyboard.inline_keyboard[0][0].text


def test_date_format_button_reflects_user_preference_mdy() -> None:
    i18n = LocalizationService("en")
    keyboard = _settings_keyboard(i18n, date_format="mdy")
    assert "MM.DD.YY" in keyboard.inline_keyboard[0][0].text


def test_date_format_callback_data() -> None:
    cb = SettingsDateFormatCallback(value="dmy")
    unpacked = SettingsDateFormatCallback.unpack(cb.pack())
    assert unpacked.value == "dmy"

    cb = SettingsDateFormatCallback(value="mdy")
    unpacked = SettingsDateFormatCallback.unpack(cb.pack())
    assert unpacked.value == "mdy"


def test_date_format_keyboard() -> None:
    i18n = LocalizationService("en")
    keyboard = _date_format_keyboard(i18n)
    assert len(keyboard.inline_keyboard) == 3
    assert "DD.MM.YY" in keyboard.inline_keyboard[0][0].text
    assert "MM.DD.YY" in keyboard.inline_keyboard[1][0].text
    assert "Back" in keyboard.inline_keyboard[2][0].text


def test_settings_no_language_button() -> None:
    """Language selection must not appear in settings."""
    i18n = LocalizationService("en")
    keyboard = _settings_keyboard(i18n)
    texts = [row[0].text for row in keyboard.inline_keyboard]
    assert not any("Language" in t for t in texts)
