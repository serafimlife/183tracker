"""Tests for stay management from /history (manage button, selection, edit, delete)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.handlers.history_command as history_handler
import app.services.history_service as history_module
from app.models.stay import Stay
from app.models.user import User
from app.services.history_service import HistoryService, MessageResult
from app.services.stay_service import (
    StayCommandConflict,
    StayService,
    StayUpdateError,
    StayUpdateSuccess,
)


class FixedDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2026, 5, 30)


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
    telegram_id: int = 100,
    *,
    entry: str,
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


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(history_module, "date", FixedDate)


@pytest.fixture
def service() -> HistoryService:
    session = AsyncMock()
    svc = HistoryService(session)
    svc._repo = AsyncMock()
    return svc


@pytest.fixture
def stay_service() -> StayService:
    session = AsyncMock()
    svc = StayService(session)
    svc._repo = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# Manage button visibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manage_button_appears_when_stays_exist(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-05-17"),
    ]

    result = await service.handle_history_command(user, "/history 2026")

    assert result.keyboard is not None
    all_buttons = [b for row in result.keyboard.inline_keyboard for b in row]
    texts = [b.text for b in all_buttons]
    assert "⚙️ Manage stay" in texts


@pytest.mark.asyncio
async def test_manage_button_absent_when_no_stays(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = []

    result = await service.handle_history_command(user, "/history 2026")

    assert result.keyboard is not None
    all_buttons = [b for row in result.keyboard.inline_keyboard for b in row]
    texts = [b.text for b in all_buttons]
    assert "⚙️ Manage stay" not in texts


# ---------------------------------------------------------------------------
# Stay selection from history page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manage_selection_shows_numbered_buttons(service: HistoryService) -> None:
    user = _user()
    stays = [
        _stay(10, entry="2026-05-17"),
        _stay(11, entry="2026-02-25", exit="2026-05-16", code="ID", name="Indonesia"),
    ]
    service._repo.list_by_user.return_value = stays

    result = await service.get_manage_selection(user, filter_key="y2026", page=0)

    assert "Select stay to manage:" in result.message
    assert result.keyboard is not None
    # First row: numbered buttons (2 stays)
    number_row = result.keyboard.inline_keyboard[0]
    assert [b.text for b in number_row] == ["1", "2"]
    # Callback data must carry actual stay IDs, not visible numbers
    cb_data = [b.callback_data or "" for b in number_row]
    assert any("10" in d for d in cb_data)
    assert any("11" in d for d in cb_data)
    # No raw ID visible in button text
    assert all(b.text.isdigit() for b in number_row)


@pytest.mark.asyncio
async def test_manage_selection_back_button_returns_to_history(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(5, entry="2026-01-01", exit="2026-01-10")
    ]

    result = await service.get_manage_selection(user, filter_key="y2026", page=0)

    assert result.keyboard is not None
    back_row = result.keyboard.inline_keyboard[-1]
    assert back_row[0].text == "⬅ Back"
    assert "hist:" in (back_row[0].callback_data or "")


# ---------------------------------------------------------------------------
# Delete confirmation flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_confirmation_shows_stay_details(service: HistoryService) -> None:
    user = _user()
    stay = _stay(7, entry="2026-05-17")
    service._repo.get_by_id.return_value = stay

    result = await service.get_stay_delete_confirmation(
        user, stay_id=7, page=0, filter_key="y2026"
    )

    assert "Delete this stay?" in result.message
    assert "Thailand" in result.message
    assert result.keyboard is not None
    all_texts = [b.text for row in result.keyboard.inline_keyboard for b in row]
    assert "✅ Confirm delete" in all_texts
    assert "❌ Cancel" in all_texts


@pytest.mark.asyncio
async def test_delete_confirmation_rejects_foreign_stay(
    service: HistoryService,
) -> None:
    user = _user(100)
    service._repo.get_by_id.return_value = _stay(7, telegram_id=999, entry="2026-05-17")

    result = await service.get_stay_delete_confirmation(
        user, stay_id=7, page=0, filter_key="y2026"
    )

    assert "not found" in result.message.lower()
    assert result.keyboard is None


# ---------------------------------------------------------------------------
# Successful deletion — StayService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_delete_calls_repo_delete(stay_service: StayService) -> None:
    user = _user(100)
    stay = _stay(3, telegram_id=100, entry="2026-01-01", exit="2026-01-10")
    stay_service._repo.get_by_id.return_value = stay

    result = await stay_service.remove_stay(user, 3)

    assert isinstance(result, StayUpdateSuccess.__bases__[0]) or hasattr(
        result, "message"
    )
    stay_service._repo.delete.assert_awaited_once_with(stay)


# ---------------------------------------------------------------------------
# History refreshes after confirm-delete callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_delete_handler_refreshes_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    callback = SimpleNamespace(
        from_user=SimpleNamespace(
            id=user.telegram_id, username="tester", first_name="Test"
        ),
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    callback_data = SimpleNamespace(stay_id=5, page=0, filter_key="y2026")

    class FakeUserService:
        def __init__(self, session: object) -> None:
            pass

        async def get_or_create(self, *a: object, **kw: object) -> tuple[User, bool]:
            return user, False

    class FakeStayService:
        def __init__(self, session: object) -> None:
            pass

        async def remove_stay(self, user: User, stay_id: int) -> object:
            return SimpleNamespace(message="removed")

    class FakeHistoryService:
        def __init__(self, session: object) -> None:
            pass

        async def handle_history_callback(
            self, user: User, filter_key: str, *, page: int
        ) -> MessageResult:
            return MessageResult(message="refreshed history", keyboard=MagicMock())

    monkeypatch.setattr(history_handler, "UserService", FakeUserService)
    monkeypatch.setattr(history_handler, "StayService", FakeStayService)
    monkeypatch.setattr(history_handler, "HistoryService", FakeHistoryService)

    await history_handler.on_manage_confirm_delete(callback, callback_data, AsyncMock())

    callback.message.edit_text.assert_awaited_once()
    text = callback.message.edit_text.call_args[0][0]
    assert text == "refreshed history"


# ---------------------------------------------------------------------------
# Edit — country
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_country_success(stay_service: StayService) -> None:
    user = _user(100)
    stay = _stay(1, telegram_id=100, entry="2026-01-01", exit="2026-01-10")
    stay_service._repo.get_by_id.return_value = stay
    stay_service._repo.update_stay.return_value = stay

    result = await stay_service.update_stay_country(user, 1, "Indonesia")

    assert isinstance(result, StayUpdateSuccess)
    assert "updated" in result.message.lower()
    stay_service._repo.update_stay.assert_awaited_once()
    call_kwargs = stay_service._repo.update_stay.call_args.kwargs
    assert call_kwargs["country_code"] == "ID"
    assert call_kwargs["country_name"] == "Indonesia"


@pytest.mark.asyncio
async def test_edit_country_unrecognized(stay_service: StayService) -> None:
    user = _user(100)
    stay_service._repo.get_by_id.return_value = _stay(
        1, telegram_id=100, entry="2026-01-01"
    )

    result = await stay_service.update_stay_country(user, 1, "Narnia")

    assert isinstance(result, StayUpdateError)
    stay_service._repo.update_stay.assert_not_called()


# ---------------------------------------------------------------------------
# Edit — entry date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_entry_date_success(stay_service: StayService) -> None:
    user = _user(100)
    stay = _stay(1, telegram_id=100, entry="2026-01-05", exit="2026-01-20")
    stay_service._repo.get_by_id.return_value = stay
    stay_service._repo.list_by_user.return_value = [stay]
    stay_service._repo.update_stay.return_value = stay

    result = await stay_service.update_stay_entry_date(user, 1, "01.01.26")

    assert isinstance(result, StayUpdateSuccess)
    stay_service._repo.update_stay.assert_awaited_once()
    call_kwargs = stay_service._repo.update_stay.call_args.kwargs
    assert call_kwargs["entry_date"] == date(2026, 1, 1)


@pytest.mark.asyncio
async def test_edit_entry_date_after_exit_rejected(stay_service: StayService) -> None:
    user = _user(100)
    stay = _stay(1, telegram_id=100, entry="2026-01-01", exit="2026-01-10")
    stay_service._repo.get_by_id.return_value = stay

    result = await stay_service.update_stay_entry_date(user, 1, "20.01.26")

    assert isinstance(result, StayUpdateError)
    stay_service._repo.update_stay.assert_not_called()


# ---------------------------------------------------------------------------
# Edit — exit date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_exit_date_success(stay_service: StayService) -> None:
    user = _user(100)
    stay = _stay(1, telegram_id=100, entry="2026-01-01", exit="2026-01-10")
    stay_service._repo.get_by_id.return_value = stay
    stay_service._repo.list_by_user.return_value = [stay]
    stay_service._repo.update_stay.return_value = stay

    result = await stay_service.update_stay_exit_date(user, 1, "20.01.26")

    assert isinstance(result, StayUpdateSuccess)
    call_kwargs = stay_service._repo.update_stay.call_args.kwargs
    assert call_kwargs["new_exit_date"] == date(2026, 1, 20)
    assert not call_kwargs["clear_exit"]


@pytest.mark.asyncio
async def test_edit_exit_date_before_entry_rejected(stay_service: StayService) -> None:
    user = _user(100)
    stay = _stay(1, telegram_id=100, entry="2026-01-10", exit="2026-01-20")
    stay_service._repo.get_by_id.return_value = stay

    result = await stay_service.update_stay_exit_date(user, 1, "05.01.26")

    assert isinstance(result, StayUpdateError)
    stay_service._repo.update_stay.assert_not_called()


@pytest.mark.asyncio
async def test_edit_exit_date_clear_with_present(stay_service: StayService) -> None:
    user = _user(100)
    stay = _stay(1, telegram_id=100, entry="2026-01-01", exit="2026-01-10")
    stay_service._repo.get_by_id.return_value = stay
    stay_service._repo.list_by_user.return_value = [stay]
    stay_service._repo.update_stay.return_value = stay

    result = await stay_service.update_stay_exit_date(user, 1, "Present")

    assert isinstance(result, StayUpdateSuccess)
    call_kwargs = stay_service._repo.update_stay.call_args.kwargs
    assert call_kwargs["clear_exit"] is True


# ---------------------------------------------------------------------------
# Overlap rejection during edit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_entry_overlap_rejected(stay_service: StayService) -> None:
    user = _user(100)
    target = _stay(1, telegram_id=100, entry="2026-03-01", exit="2026-03-20")
    blocker = _stay(2, telegram_id=100, entry="2026-01-01", exit="2026-03-10")
    stay_service._repo.get_by_id.return_value = target
    stay_service._repo.list_by_user.return_value = [target, blocker]

    # Moving entry_date to 2026-01-05 would overlap with blocker
    result = await stay_service.update_stay_entry_date(user, 1, "05.01.26")

    assert isinstance(result, StayCommandConflict)
    stay_service._repo.update_stay.assert_not_called()


# ---------------------------------------------------------------------------
# History refreshes after successful edit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_edit_country_handler_refreshes_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    message = SimpleNamespace(
        from_user=SimpleNamespace(
            id=user.telegram_id, username="tester", first_name="Test"
        ),
        text="Indonesia",
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        clear=AsyncMock(),
        get_data=AsyncMock(
            return_value={
                "manage_stay_id": 5,
                "manage_page": 0,
                "manage_filter_key": "y2026",
            }
        ),
    )

    class FakeUserService:
        def __init__(self, session: object) -> None:
            pass

        async def get_or_create(self, *a: object, **kw: object) -> tuple[User, bool]:
            return user, False

    class FakeStayService:
        def __init__(self, session: object) -> None:
            pass

        async def update_stay_country(
            self, user: User, stay_id: int, country_input: str
        ) -> StayUpdateSuccess:
            return StayUpdateSuccess(message="✅ Stay updated.")

    class FakeHistoryService:
        def __init__(self, session: object) -> None:
            pass

        async def handle_history_callback(
            self, user: User, filter_key: str, *, page: int
        ) -> MessageResult:
            assert filter_key == "y2026"
            assert page == 0
            return MessageResult(message="refreshed", keyboard=MagicMock())

    monkeypatch.setattr(history_handler, "UserService", FakeUserService)
    monkeypatch.setattr(history_handler, "StayService", FakeStayService)
    monkeypatch.setattr(history_handler, "HistoryService", FakeHistoryService)

    await history_handler.on_manage_edit_country_input(message, state, AsyncMock())

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()
    assert message.answer.call_args[0][0] == "refreshed"
