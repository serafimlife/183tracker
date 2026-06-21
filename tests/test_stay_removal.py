"""Tests for stay removal and conflict handling."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.stay import Stay
from app.models.user import User
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandError,
    StayCommandSuccess,
    StayRemoveError,
    StayRemoveSuccess,
    StayService,
)


def _user(telegram_id: int = 100) -> User:
    return User(
        telegram_id=telegram_id,
        username="tester",
        first_name="Test",
        language="en",
        date_format="dmy",
    )


def _stay(
    stay_id: int,
    telegram_id: int,
    *,
    entry: str = "2026-05-17",
    exit: str | None = None,
    code: str = "TH",
    name: str = "Thailand",
) -> Stay:
    return Stay(
        id=stay_id,
        telegram_id=telegram_id,
        country_code=code,
        country_name=name,
        entry_date=date.fromisoformat(entry),
        exit_date=date.fromisoformat(exit) if exit else None,
    )


@pytest.fixture
def service() -> StayService:
    session = AsyncMock()
    svc = StayService(session)
    svc._repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_remove_own_stay(service: StayService) -> None:
    user = _user(100)
    stay = _stay(1, 100)
    service._repo.get_by_id.return_value = stay

    result = await service.remove_stay(user, 1)

    assert isinstance(result, StayRemoveSuccess)
    service._repo.delete.assert_awaited_once_with(stay)


@pytest.mark.asyncio
async def test_remove_nonexistent_stay(service: StayService) -> None:
    user = _user()
    service._repo.get_by_id.return_value = None

    result = await service.remove_stay(user, 999)

    assert isinstance(result, StayRemoveError)
    service._repo.delete.assert_not_called()


@pytest.mark.asyncio
async def test_remove_another_users_stay(service: StayService) -> None:
    user = _user(100)
    service._repo.get_by_id.return_value = _stay(1, 200)

    result = await service.remove_stay(user, 1)

    assert isinstance(result, StayRemoveError)
    service._repo.delete.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_in_returns_conflict_with_keyboard(
    service: StayService,
) -> None:
    user = _user()
    existing = [_stay(1, user.telegram_id)]
    service._repo.list_by_user.return_value = existing

    result = await service.handle_in_command(user, "/in Thailand 17.05.26")

    assert isinstance(result, StayCommandConflict)
    assert result.keyboard.inline_keyboard
    assert "rm_stay" in result.keyboard.inline_keyboard[0][0].callback_data
    service._repo.create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_out_returns_conflict(service: StayService) -> None:
    user = _user()
    closed = _stay(1, user.telegram_id, entry="2026-01-01", exit="2026-08-30")
    service._repo.list_by_user.return_value = [closed]
    service._repo.get_open_stay.return_value = None

    result = await service.handle_out_command(user, "/out Thailand 30.08.26")

    assert isinstance(result, StayCommandConflict)
    service._repo.close_stay.assert_not_called()


@pytest.mark.asyncio
async def test_out_closed_latest_stay_suggests_correction(service: StayService) -> None:
    user = _user()
    older = _stay(
        1,
        user.telegram_id,
        entry="2026-01-01",
        exit="2026-01-15",
        code="ID",
        name="Indonesia",
    )
    latest = _stay(
        2,
        user.telegram_id,
        entry="2026-02-25",
        exit="2026-05-17",
        code="ID",
        name="Indonesia",
    )
    service._repo.list_by_user.return_value = [older, latest]
    service._repo.get_open_stay.return_value = None

    result = await service.handle_out_command(user, "/out Indonesia 16.05.26")

    assert isinstance(result, StayCommandConflict)
    assert "Your latest 🇮🇩 Indonesia stay is already closed" in result.message
    assert "25 February 2026 → 17 May 2026" in result.message
    button = result.keyboard.inline_keyboard[0][0]
    assert button.text == "Remove Indonesia 25.02.26–17.05.26"
    assert "rm_stay" in button.callback_data
    assert "2" in button.callback_data
    service._repo.close_stay.assert_not_called()


@pytest.mark.asyncio
async def test_out_closed_stay_unrelated_country_no_correction(
    service: StayService,
) -> None:
    user = _user()
    indonesia = _stay(
        1,
        user.telegram_id,
        entry="2026-02-25",
        exit="2026-05-17",
        code="ID",
        name="Indonesia",
    )
    service._repo.list_by_user.return_value = [indonesia]
    service._repo.get_open_stay.return_value = None

    result = await service.handle_out_command(user, "/out Thailand 16.05.26")

    assert isinstance(result, StayCommandError)
    assert result.message == "No open stay found for Thailand. Use `/in` first."
    service._repo.close_stay.assert_not_called()


@pytest.mark.asyncio
async def test_out_no_history_no_correction(service: StayService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = []
    service._repo.get_open_stay.return_value = None

    result = await service.handle_out_command(user, "/out Indonesia 16.05.26")

    assert isinstance(result, StayCommandError)
    assert result.message == "No open stay found for Indonesia. Use `/in` first."
    service._repo.close_stay.assert_not_called()


@pytest.mark.asyncio
async def test_out_already_correct_exit_date_uses_duplicate_conflict(
    service: StayService,
) -> None:
    user = _user()
    indonesia = _stay(
        1,
        user.telegram_id,
        entry="2026-02-25",
        exit="2026-05-17",
        code="ID",
        name="Indonesia",
    )
    service._repo.list_by_user.return_value = [indonesia]
    service._repo.get_open_stay.return_value = None

    result = await service.handle_out_command(user, "/out Indonesia 17.05.26")

    assert isinstance(result, StayCommandConflict)
    assert "This stay already exists" in result.message
    assert "Your latest" not in result.message
    service._repo.close_stay.assert_not_called()


@pytest.mark.asyncio
async def test_historical_open_stay_can_be_closed_before_active_stay(
    service: StayService,
) -> None:
    user = _user()
    indonesia = _stay(
        1,
        user.telegram_id,
        entry="2026-02-25",
        code="ID",
        name="Indonesia",
    )
    thailand = _stay(
        2,
        user.telegram_id,
        entry="2026-05-17",
        code="TH",
        name="Thailand",
    )
    service._repo.list_by_user.return_value = [indonesia, thailand]
    service._repo.get_open_stay.return_value = indonesia

    result = await service.handle_out_command(user, "/out Indonesia 16.05.26")

    assert isinstance(result, StayCommandSuccess)
    service._repo.close_stay.assert_awaited_once_with(indonesia, date(2026, 5, 16))
