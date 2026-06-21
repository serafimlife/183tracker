"""Tests for onboarding flow (no language selection)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.bot.callbacks.onboarding import OnboardingDateFormatCallback
from app.bot.states.onboarding import OnboardingStates
from app.services.onboarding_service import OnboardingService
from app.utils.onboarding import DEFAULT_LANGUAGE, DateFormat


def _make_user(
    *,
    language: str | None = None,
    date_format: str | None = None,
    is_onboarded: bool = False,
) -> MagicMock:
    user = MagicMock()
    user.telegram_id = 1
    user.language = language
    user.date_format = date_format
    user.is_onboarded = is_onboarded
    user.first_name = "Alice"
    return user


@pytest.mark.asyncio
async def test_start_onboarding_sets_default_language() -> None:
    """start_onboarding persists DEFAULT_LANGUAGE and shows date format picker."""
    session = AsyncMock()
    repo = AsyncMock()
    user = _make_user()

    service = OnboardingService(session)
    service._repo = repo

    step = await service.start_onboarding(user)

    repo.set_language.assert_awaited_once_with(user, DEFAULT_LANGUAGE)
    assert step.fsm_state == OnboardingStates.date_format
    assert step.keyboard is not None


def test_start_onboarding_no_language_keyboard() -> None:
    """The onboarding keyboard must offer date formats, not language choices."""
    from app.bot.callbacks.onboarding import OnboardingDateFormatCallback
    from app.utils.onboarding import DateFormat

    cb_dmy = OnboardingDateFormatCallback(value=DateFormat.DMY).pack()
    cb_mdy = OnboardingDateFormatCallback(value=DateFormat.MDY).pack()

    assert "ob_date" in cb_dmy
    assert "ob_date" in cb_mdy
    assert "ob_lang" not in cb_dmy


@pytest.mark.asyncio
async def test_select_date_format_completes_onboarding() -> None:
    session = AsyncMock()
    repo = AsyncMock()
    user = _make_user(language=DEFAULT_LANGUAGE)

    service = OnboardingService(session)
    service._repo = repo

    step = await service.select_date_format(user, DateFormat.DMY)

    repo.set_date_format.assert_awaited_once_with(user, DateFormat.DMY.value)
    assert step.clear_fsm is True
    assert step.keyboard is None


@pytest.mark.asyncio
async def test_onboarding_complete_text_mentions_import() -> None:
    """Completion message must promote /import for existing travelers."""
    session = AsyncMock()
    repo = AsyncMock()
    user = _make_user(language=DEFAULT_LANGUAGE)

    service = OnboardingService(session)
    service._repo = repo

    step = await service.select_date_format(user, DateFormat.DMY)

    assert "/import" in step.text


def test_resume_onboarding_shows_date_format() -> None:
    """Users who partially completed onboarding go straight to date format."""
    session = AsyncMock()
    user = _make_user(language=DEFAULT_LANGUAGE)

    service = OnboardingService(session)
    step = service.resume_onboarding(user)

    assert step.fsm_state == OnboardingStates.date_format
    assert step.keyboard is not None


def test_onboarding_states_has_no_language_state() -> None:
    """Language state must be gone from OnboardingStates."""
    assert not hasattr(OnboardingStates, "language")
    assert hasattr(OnboardingStates, "date_format")


def test_default_language_is_english() -> None:
    assert DEFAULT_LANGUAGE == "en"
