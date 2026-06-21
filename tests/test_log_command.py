"""Tests for completed-stay `/log` creation."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.states.log_command import LogCommandStates
from app.handlers import log_command
from app.models.stay import Stay
from app.models.user import User
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandError,
    StayCommandSuccess,
    StayService,
)


class FakeState:
    def __init__(self) -> None:
        self.current = None
        self.data: dict[str, str] = {}

    async def set_state(self, value) -> None:
        self.current = value

    async def update_data(self, **kwargs) -> None:
        self.data.update(kwargs)

    async def get_data(self) -> dict[str, str]:
        return dict(self.data)

    async def clear(self) -> None:
        self.current = None
        self.data.clear()


def _user() -> User:
    return User(
        telegram_id=303,
        username="u",
        first_name="n",
        language="en",
        date_format="dmy",
    )


def _stay(
    stay_id: int = 1,
    *,
    entry: str = "2026-01-01",
    exit: str | None = "2026-01-15",
    code: str = "TH",
    name: str = "Thailand",
) -> Stay:
    return Stay(
        id=stay_id,
        telegram_id=303,
        country_code=code,
        country_name=name,
        entry_date=date.fromisoformat(entry),
        exit_date=date.fromisoformat(exit) if exit else None,
    )


def _message(text: str):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=303, username="u", first_name="n"),
        answer=AsyncMock(),
    )


@pytest.fixture
def service() -> StayService:
    svc = StayService(AsyncMock())
    svc._repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_direct_command_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_log_command(self, user, command_text: str):
        assert command_text == "/log Thailand 01.01.26 15.01.26"
        return StayCommandSuccess(message="logged")

    monkeypatch.setattr(log_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        log_command.StayService,
        "handle_log_command",
        fake_handle_log_command,
    )

    state = FakeState()
    message = _message("/log Thailand 01.01.26 15.01.26")
    await log_command.cmd_log(message, state, session=AsyncMock())

    assert state.current is None
    message.answer.assert_awaited_once_with("logged")


@pytest.mark.asyncio
async def test_fsm_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_log_command(self, user, command_text: str):
        assert command_text == "/log Thailand 01.01.26 15.01.26"
        return StayCommandSuccess(message="logged")

    monkeypatch.setattr(log_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        log_command.StayService,
        "handle_log_command",
        fake_handle_log_command,
    )

    state = FakeState()
    await log_command.cmd_log(_message("/log"), state, session=AsyncMock())
    assert state.current == LogCommandStates.awaiting_country

    await log_command.log_waiting_country(
        _message("Thailand"), state, session=AsyncMock()
    )
    assert state.current == LogCommandStates.awaiting_entry_date

    await log_command.log_waiting_entry_date(
        _message("01.01.26"), state, session=AsyncMock()
    )
    assert state.current == LogCommandStates.awaiting_exit_date

    message = _message("15.01.26")
    await log_command.log_waiting_exit_date(message, state, session=AsyncMock())

    assert state.current is None
    message.answer.assert_awaited_once_with("logged")


@pytest.mark.asyncio
async def test_fsm_invalid_entry_date_rerequests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid entry date is caught immediately — state stays at awaiting_entry_date."""

    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    monkeypatch.setattr(log_command.UserService, "get_or_create", fake_get_or_create)

    state = FakeState()
    await log_command.cmd_log(_message("/log"), state, session=AsyncMock())
    await log_command.log_waiting_country(
        _message("Thailand"), state, session=AsyncMock()
    )
    assert state.current == LogCommandStates.awaiting_entry_date

    bad_date = _message("not-a-date")
    await log_command.log_waiting_entry_date(bad_date, state, session=AsyncMock())

    assert state.current == LogCommandStates.awaiting_entry_date
    bad_date.answer.assert_awaited_once()
    assert "Invalid" in bad_date.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_fsm_command_escape_clears_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Typing a slash command while in log FSM clears state instead of looping."""

    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    dispatched: list[str] = []

    async def fake_cmd_history(message, session):
        dispatched.append("history")

    monkeypatch.setattr(log_command.UserService, "get_or_create", fake_get_or_create)

    import app.handlers.history_command as hc_module

    monkeypatch.setattr(hc_module, "cmd_history", fake_cmd_history)

    state = FakeState()
    await log_command.cmd_log(_message("/log"), state, session=AsyncMock())
    await log_command.log_waiting_country(
        _message("Thailand"), state, session=AsyncMock()
    )

    # User types /history while waiting for entry date
    escape_msg = _message("/history")
    await log_command.log_waiting_entry_date(escape_msg, state, session=AsyncMock())

    assert state.current is None
    assert dispatched == ["history"]


@pytest.mark.asyncio
async def test_fsm_error_clears_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """StayCommandError on exit-date step clears FSM state so user isn't stuck."""

    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_log_command(self, user, command_text: str):
        return StayCommandError(message="❌ Conflict")

    monkeypatch.setattr(log_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        log_command.StayService,
        "handle_log_command",
        fake_handle_log_command,
    )

    state = FakeState()
    await log_command.cmd_log(_message("/log"), state, session=AsyncMock())
    await log_command.log_waiting_country(
        _message("Thailand"), state, session=AsyncMock()
    )
    await log_command.log_waiting_entry_date(
        _message("01.01.26"), state, session=AsyncMock()
    )

    message = _message("15.01.26")
    await log_command.log_waiting_exit_date(message, state, session=AsyncMock())

    assert state.current is None
    message.answer.assert_awaited_once_with("❌ Conflict")


@pytest.mark.asyncio
async def test_completed_stay_creation_is_inclusive(service: StayService) -> None:
    service._repo.list_by_user.return_value = []
    created = _stay(exit=None)
    service._repo.create_entry.return_value = created

    result = await service.handle_log_command(
        _user(),
        "/log Thailand 01.01.26 15.01.26",
    )

    assert isinstance(result, StayCommandSuccess)
    assert "15 days" in result.message
    service._repo.create_entry.assert_awaited_once()
    service._repo.close_stay.assert_awaited_once_with(
        created,
        date(2026, 1, 15),
    )


@pytest.mark.asyncio
async def test_invalid_date_order(service: StayService) -> None:
    result = await service.handle_log_command(
        _user(),
        "/log Thailand 15.01.26 01.01.26",
    )

    assert isinstance(result, StayCommandError)
    assert "before entry" in result.message
    service._repo.create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_overlap_rejection(service: StayService) -> None:
    service._repo.list_by_user.return_value = [
        _stay(entry="2026-01-10", exit="2026-01-20")
    ]

    result = await service.handle_log_command(
        _user(),
        "/log Japan 01.01.26 15.01.26",
    )

    assert isinstance(result, StayCommandConflict)
    service._repo.create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_country(service: StayService) -> None:
    result = await service.handle_log_command(
        _user(),
        "/log Not A Country 01.01.26 15.01.26",
    )

    assert isinstance(result, StayCommandError)
    assert "Country not recognized" in result.message
    service._repo.create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_multi_word_country(service: StayService) -> None:
    service._repo.list_by_user.return_value = []
    created = _stay(exit=None, code="US", name="United States")
    service._repo.create_entry.return_value = created

    result = await service.handle_log_command(
        _user(),
        "/log United States 01.01.26 15.01.26",
    )

    assert isinstance(result, StayCommandSuccess)
    service._repo.create_entry.assert_awaited_once_with(
        303,
        country_code="US",
        country_name="United States",
        entry_date=date(2026, 1, 1),
    )
