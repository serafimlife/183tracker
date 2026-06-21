from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.states.out_command import OutCommandStates
from app.handlers import out_command
from app.models.user import User
from app.services.stay_service import StayCommandError, StayCommandSuccess


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
        telegram_id=202,
        username="u",
        first_name="n",
        language="en",
        date_format="dmy",
    )


def _message(text: str):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=202, username="u", first_name="n"),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_out_no_args_prompts_for_country(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    monkeypatch.setattr(out_command.UserService, "get_or_create", fake_get_or_create)
    message = _message("/out")
    state = FakeState()

    await out_command.cmd_out(message, state, session=AsyncMock())

    assert state.current == OutCommandStates.awaiting_country
    message.answer.assert_awaited_once_with(
        "Which country do you want to add exit for?"
    )


@pytest.mark.asyncio
async def test_out_country_only_prompts_for_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    monkeypatch.setattr(out_command.UserService, "get_or_create", fake_get_or_create)
    message = _message("/out Thailand")
    state = FakeState()

    await out_command.cmd_out(message, state, session=AsyncMock())

    assert state.current == OutCommandStates.awaiting_date
    assert state.data["out_pending_country"] == "Thailand"
    message.answer.assert_awaited_once_with(
        "What is the exit date for Thailand?\n\nExamples:\n- today\n- yesterday\n- 24.05.26"
    )


@pytest.mark.asyncio
async def test_out_interactive_flow_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_out_command(self, user, command_text: str):
        assert command_text == "/out Thailand today"
        return StayCommandSuccess(message="closed")

    monkeypatch.setattr(out_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        out_command.StayService, "handle_out_command", fake_handle_out_command
    )

    state = FakeState()
    await out_command.out_waiting_country(
        _message("Thailand"), state, session=AsyncMock()
    )
    message = _message("today")
    await out_command.out_waiting_date(message, state, session=AsyncMock())

    assert state.current is None
    message.answer.assert_awaited_once_with("closed")


@pytest.mark.asyncio
async def test_out_interactive_invalid_country_and_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_out_command(self, user, command_text: str):
        return StayCommandError(message="❌ Invalid date.")

    monkeypatch.setattr(out_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        out_command.StayService, "handle_out_command", fake_handle_out_command
    )

    state = FakeState()
    bad_country_message = _message("NoCountry")
    await out_command.out_waiting_country(
        bad_country_message, state, session=AsyncMock()
    )
    bad_country_message.answer.assert_awaited_once()
    assert state.current is None

    await state.set_state(OutCommandStates.awaiting_date)
    await state.update_data(out_pending_country="Thailand")
    bad_date_message = _message("not-a-date")
    await out_command.out_waiting_date(bad_date_message, state, session=AsyncMock())
    assert state.current == OutCommandStates.awaiting_date
    bad_date_message.answer.assert_awaited_once_with("❌ Invalid date.")


@pytest.mark.asyncio
async def test_out_one_line_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_out_command(self, user, command_text: str):
        assert command_text == "/out Thailand today"
        return StayCommandSuccess(message="done")

    monkeypatch.setattr(out_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        out_command.StayService, "handle_out_command", fake_handle_out_command
    )

    message = _message("/out Thailand today")
    state = FakeState()
    await out_command.cmd_out(message, state, session=AsyncMock())
    message.answer.assert_awaited_once_with("done")


@pytest.mark.asyncio
async def test_out_pending_country_command_has_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    where_called = {"ok": False}

    async def fake_cmd_where(message, session):
        where_called["ok"] = True

    monkeypatch.setattr(out_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr("app.handlers.where_command.cmd_where", fake_cmd_where)

    state = FakeState()
    await state.set_state(OutCommandStates.awaiting_country)
    message = _message("/where")
    await out_command.out_waiting_country(message, state, session=AsyncMock())

    assert where_called["ok"] is True
    assert state.current is None
