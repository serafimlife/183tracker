from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.states.in_command import InCommandStates
from app.handlers import in_command
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
        telegram_id=101,
        username="u",
        first_name="n",
        language="en",
        date_format="dmy",
    )


def _message(text: str):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=101, username="u", first_name="n"),
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_in_no_args_prompts_for_country(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    monkeypatch.setattr(in_command.UserService, "get_or_create", fake_get_or_create)
    message = _message("/in")
    state = FakeState()

    await in_command.cmd_in(message, state, session=AsyncMock())

    assert state.current == InCommandStates.awaiting_country
    message.answer.assert_awaited_once_with(
        "Which country do you want to add entry to?"
    )


@pytest.mark.asyncio
async def test_in_country_only_prompts_for_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    monkeypatch.setattr(in_command.UserService, "get_or_create", fake_get_or_create)
    message = _message("/in Thailand")
    state = FakeState()

    await in_command.cmd_in(message, state, session=AsyncMock())

    assert state.current == InCommandStates.awaiting_date
    assert state.data["in_pending_country"] == "Thailand"
    message.answer.assert_awaited_once_with(
        "What is the entry date for Thailand?\n\nExamples:\n- today\n- yesterday\n- 24.05.26"
    )


@pytest.mark.asyncio
async def test_interactive_flow_success_with_tip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_in_command(self, user, command_text: str):
        assert command_text == "/in Thailand today"
        return StayCommandSuccess(message="ok")

    monkeypatch.setattr(in_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        in_command.StayService, "handle_in_command", fake_handle_in_command
    )

    state = FakeState()
    await in_command.in_waiting_country(
        _message("Thailand"), state, session=AsyncMock()
    )
    message = _message("today")
    await in_command.in_waiting_date(message, state, session=AsyncMock())

    assert state.current is None
    assert message.answer.await_count == 2
    message.answer.assert_any_await("ok")
    message.answer.assert_any_await(
        "Tip: you can also do this faster with:\n\n/in Thailand today"
    )


@pytest.mark.asyncio
async def test_interactive_invalid_country_and_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_in_command(self, user, command_text: str):
        return StayCommandError(message="❌ Invalid date.")

    monkeypatch.setattr(in_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        in_command.StayService, "handle_in_command", fake_handle_in_command
    )

    state = FakeState()
    invalid_country_message = _message("NowhereLand")
    await in_command.in_waiting_country(
        invalid_country_message, state, session=AsyncMock()
    )
    invalid_country_message.answer.assert_awaited_once()
    assert state.current is None

    await state.set_state(InCommandStates.awaiting_date)
    await state.update_data(in_pending_country="Thailand")
    invalid_date_message = _message("not-a-date")
    await in_command.in_waiting_date(invalid_date_message, state, session=AsyncMock())
    assert state.current == InCommandStates.awaiting_date
    invalid_date_message.answer.assert_awaited_once_with("❌ Invalid date.")


@pytest.mark.asyncio
async def test_one_line_in_command_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    async def fake_handle_in_command(self, user, command_text: str):
        assert command_text == "/in Thailand today"
        return StayCommandSuccess(message="done")

    monkeypatch.setattr(in_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr(
        in_command.StayService, "handle_in_command", fake_handle_in_command
    )

    message = _message("/in Thailand today")
    state = FakeState()
    await in_command.cmd_in(message, state, session=AsyncMock())
    message.answer.assert_awaited_once_with("done")


@pytest.mark.asyncio
async def test_in_pending_country_command_has_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get_or_create(*args, **kwargs):
        return _user(), False

    settings_called = {"ok": False}

    async def fake_cmd_settings(message, session):
        settings_called["ok"] = True

    monkeypatch.setattr(in_command.UserService, "get_or_create", fake_get_or_create)
    monkeypatch.setattr("app.handlers.settings.cmd_settings", fake_cmd_settings)

    state = FakeState()
    await state.set_state(InCommandStates.awaiting_country)
    message = _message("/settings")
    await in_command.in_waiting_country(message, state, session=AsyncMock())

    assert settings_called["ok"] is True
    assert state.current is None
