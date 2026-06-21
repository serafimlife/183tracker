"""Tests for /where, /history, and shared duration formatting."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.services.history_service as history_module
import app.handlers.history_command as history_handler
from app.models.stay import Stay
from app.models.user import User
from app.services.history_service import HistoryService, MessageResult
from app.services.parsing_service import ParsingService
from app.utils.formatters import format_duration_days, get_threshold_indicator


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


def test_duration_pluralization_helper() -> None:
    assert format_duration_days(0) == "0 days"
    assert format_duration_days(1) == "1 day"
    assert format_duration_days(2) == "2 days"


def test_get_threshold_indicator() -> None:
    assert get_threshold_indicator(183) == "\U0001f7e2"
    assert get_threshold_indicator(61) == "\U0001f7e2"
    assert get_threshold_indicator(60) == "\U0001f7e1"
    assert get_threshold_indicator(31) == "\U0001f7e1"
    assert get_threshold_indicator(30) == "\U0001f534"
    assert get_threshold_indicator(0) == "\U0001f534"


@pytest.mark.asyncio
async def test_where_active_stay(service: HistoryService) -> None:
    user = _user()
    stays = [
        _stay(1, entry="2025-12-08", exit="2026-03-24"),
        _stay(2, entry="2026-05-17"),
    ]
    service._repo.list_by_user.return_value = stays

    result = await service.handle_where_command(user)

    assert "📍 Current active stay" in result.message
    assert "🇹🇭 Thailand\nEntered on 17 May 2026" in result.message
    assert "Current stay:\n14 days" in result.message
    assert "Calendar year: 97 days" in result.message
    assert "Rolling 365: 121 days" in result.message
    assert "86 days" in result.message
    assert "62 days" in result.message


@pytest.mark.asyncio
async def test_where_no_active_stay(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-02-25", exit="2026-05-17", code="ID", name="Indonesia")
    ]

    result = await service.handle_where_command(user)

    assert (
        result.message
        == "❌ No active stay found.\n\nYou can add one with:\n/in Country today"
    )


@pytest.mark.asyncio
async def test_history_defaults_to_current_year(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2025-04-01", exit="2025-04-10"),
        _stay(2, entry="2026-02-25", exit="2026-05-17", code="ID", name="Indonesia"),
    ]

    result = await service.handle_history_command(user, "/history")

    assert "Travel history — 2026" in result.message
    assert "Indonesia" in result.message
    assert "2025" not in result.message


@pytest.mark.asyncio
async def test_history_year_filtering(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2025-04-01", exit="2025-04-10"),
        _stay(2, entry="2026-02-25", exit="2026-05-17", code="ID", name="Indonesia"),
    ]

    result = await service.handle_history_command(user, "/history 2025")

    assert "Travel history — 2025" in result.message
    assert "Thailand" in result.message
    assert "Indonesia" not in result.message


@pytest.mark.asyncio
async def test_history_country_filtering(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2025-04-01", exit="2025-04-10"),
        _stay(2, entry="2026-02-25", exit="2026-05-17", code="ID", name="Indonesia"),
    ]

    result = await service.handle_history_command(user, "/history Thailand")

    assert "Travel history — Thailand" in result.message
    assert "Thailand" in result.message
    assert "Indonesia" not in result.message


@pytest.mark.asyncio
async def test_history_country_and_year_filtering(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2025-04-01", exit="2025-04-10"),
        _stay(2, entry="2026-02-25", exit="2026-05-17"),
        _stay(3, entry="2026-06-01", exit="2026-06-05", code="ID", name="Indonesia"),
    ]

    result = await service.handle_history_command(user, "/history Thailand 2026")

    assert "Travel history — Thailand — 2026" in result.message
    assert "17 May 2026" in result.message
    assert "Indonesia" not in result.message


@pytest.mark.asyncio
async def test_history_custom_date_range(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-01-01", exit="2026-01-05"),
        _stay(2, entry="2026-03-10", exit="2026-03-20", code="ID", name="Indonesia"),
    ]

    result = await service.handle_history_command(user, "/history 01.03.26 05.07.26")

    assert "Indonesia" in result.message
    assert "Jan" not in result.message


@pytest.mark.asyncio
async def test_history_custom_dates_callback_prompts(service: HistoryService) -> None:
    user = _user()

    result = await service.handle_history_callback(user, "custom_cTH", page=0)

    assert result.message.startswith("Send custom date range.")
    assert "01.03.26 05.07.26" in result.message
    assert result.fsm_data == {"history_base_filter_key": "cTH"}


@pytest.mark.asyncio
async def test_history_custom_date_range_valid(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-03-15", exit="2026-03-20", code="ID", name="Indonesia")
    ]

    result = await service.handle_custom_date_range(user, "01.03.26 05.07.26")

    assert "Travel history — 1 Mar 2026–5 Jul 2026" in result.message
    assert "Indonesia" in result.message


@pytest.mark.asyncio
async def test_history_custom_dates_preserve_country_filter(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-05-17", code="TH", name="Thailand"),
        _stay(2, entry="2026-03-10", exit="2026-03-20", code="ID", name="Indonesia"),
    ]

    result = await service.handle_custom_date_range(
        user,
        "01.03.26 05.07.26",
        base_filter_key="cTH",
    )

    assert "Travel history — Thailand — 1 Mar 2026–5 Jul 2026" in result.message
    assert "Thailand" in result.message
    assert "Indonesia" not in result.message
    # today = May 30; active stay from May 17 caps to today: 17 May–30 May = 14 days
    assert "(14 days)" in result.message


@pytest.mark.asyncio
async def test_history_custom_dates_preserve_year_filter(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2025-12-25", exit="2026-01-10", code="ID", name="Indonesia"),
        _stay(2, entry="2025-06-01", exit="2025-06-05"),
    ]

    result = await service.handle_custom_date_range(
        user,
        "20.12.25 05.01.26",
        base_filter_key="y2026",
    )

    # Custom dates now override the base year filter entirely
    assert "Travel history — 20 Dec 2025–5 Jan 2026" in result.message
    assert "Indonesia" in result.message
    # Indonesia stay: Dec 25–Jan 10, window Dec 20–Jan 5 → Dec 25–Jan 5 = 12 days
    assert "(12 days)" in result.message
    assert "Thailand" not in result.message


@pytest.mark.asyncio
async def test_history_custom_dates_preserve_country_and_year_filter(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-05-17", code="TH", name="Thailand"),
        _stay(2, entry="2026-03-10", exit="2026-03-20", code="ID", name="Indonesia"),
    ]

    result = await service.handle_custom_date_range(
        user,
        "01.03.26 05.07.26",
        base_filter_key="cyTH-2026",
    )

    assert "Travel history — Thailand — 1 Mar 2026–5 Jul 2026" in result.message
    assert "Thailand" in result.message
    assert "Indonesia" not in result.message


@pytest.mark.asyncio
async def test_history_custom_dates_empty_with_preserved_filter(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-03-10", exit="2026-03-20", code="ID", name="Indonesia"),
    ]

    result = await service.handle_custom_date_range(
        user,
        "01.03.26 05.07.26",
        base_filter_key="cTH",
    )

    assert result.message == "🧳 No stays found for this filter."


@pytest.mark.asyncio
async def test_history_custom_date_range_invalid(service: HistoryService) -> None:
    user = _user()

    result = await service.handle_custom_date_range(user, "not a range")

    assert result.message.startswith("❌ Could not parse date range.")
    assert result.keyboard is None
    service._repo.list_by_user.assert_not_called()


def test_history_date_range_dmy_and_mdy_parsing() -> None:
    dmy = ParsingService.parse_history_date_range(
        "01-03-2026 05-07-2026",
        date_format="dmy",
        today=FixedDate.today(),
    )
    mdy = ParsingService.parse_history_date_range(
        "03-01-2026 07-05-2026",
        date_format="mdy",
        today=FixedDate.today(),
    )

    assert dmy is not None
    assert dmy.start_date == date(2026, 3, 1)
    assert dmy.end_date == date(2026, 7, 5)
    assert mdy is not None
    assert mdy.start_date == date(2026, 3, 1)
    assert mdy.end_date == date(2026, 7, 5)


def test_history_custom_dates_cancel_flow(service: HistoryService) -> None:
    result = service.cancel_custom_dates(_user())

    assert result.message == "Custom date range cancelled."


@pytest.mark.asyncio
async def test_history_custom_dates_callback_stores_base_filter_in_fsm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    callback = SimpleNamespace(
        from_user=SimpleNamespace(
            id=user.telegram_id, username="tester", first_name="Test"
        ),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    callback_data = SimpleNamespace(filter_key="custom_cTH", page=0)
    state = SimpleNamespace(set_state=AsyncMock(), update_data=AsyncMock())

    class FakeUserService:
        def __init__(self, session: object) -> None:
            pass

        async def get_or_create(
            self, *args: object, **kwargs: object
        ) -> tuple[User, bool]:
            return user, False

    class FakeHistoryService:
        def __init__(self, session: object) -> None:
            pass

        async def handle_history_callback(
            self,
            user: User,
            filter_key: str,
            *,
            page: int,
        ) -> MessageResult:
            assert filter_key == "custom_cTH"
            return MessageResult(
                message="prompt",
                fsm_data={"history_base_filter_key": "cTH"},
            )

    monkeypatch.setattr(history_handler, "UserService", FakeUserService)
    monkeypatch.setattr(history_handler, "HistoryService", FakeHistoryService)

    await history_handler.on_history_page(callback, callback_data, state, AsyncMock())

    state.set_state.assert_awaited_once()
    state.update_data.assert_awaited_once_with(history_base_filter_key="cTH")
    callback.message.answer.assert_awaited_once_with("prompt")


@pytest.mark.asyncio
async def test_history_empty_state(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = []

    result = await service.handle_history_command(user, "/history 2026")

    assert result.message == "🧳 No stays found for this filter."


@pytest.mark.asyncio
async def test_history_pagination_boundaries(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(i, entry=f"2026-01-{i:02d}", exit=f"2026-01-{i:02d}")
        for i in range(1, 13)
    ]

    first = await service.handle_history_command(user, "/history 2026", page=0)
    second = await service.handle_history_command(user, "/history 2026", page=1)

    assert "Showing 1–10 of 12 stays" in first.message
    assert first.keyboard is not None
    first_buttons = [
        button.text for row in first.keyboard.inline_keyboard for button in row
    ]
    assert "Older →" in first_buttons
    assert "← Newer" not in first_buttons
    assert "Showing 11–12 of 12 stays" in second.message
    assert second.keyboard is not None
    second_buttons = [
        button.text for row in second.keyboard.inline_keyboard for button in row
    ]
    assert "← Newer" in second_buttons
    assert "Older →" not in second_buttons


@pytest.mark.asyncio
async def test_history_newest_first_sorting(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-01-01", exit="2026-01-02"),
        _stay(2, entry="2026-05-01", exit="2026-05-02", code="ID", name="Indonesia"),
    ]

    result = await service.handle_history_command(user, "/history 2026")

    assert result.message.index("Indonesia") < result.message.index("Thailand")


@pytest.mark.asyncio
async def test_history_active_stay_present_formatting(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-05-17"),
    ]

    result = await service.handle_history_command(user, "/history 2026")

    assert "17 May 2026 → Present" in result.message
    # FixedDate.today() = 2026-05-30; active stay caps to today: 17 May–30 May = 14 days
    assert "(14 days)" in result.message


@pytest.mark.asyncio
async def test_history_duration_overlap_at_range_start(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-02-25", exit="2026-05-16", code="ID", name="Indonesia")
    ]

    result = await service.handle_history_command(user, "/history 01.03.26 05.07.26")

    assert "25 Feb 2026 → 16 May 2026" in result.message
    assert "(77 days)" in result.message


@pytest.mark.asyncio
async def test_history_duration_overlap_at_range_end(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-06-20", exit="2026-07-10", code="ID", name="Indonesia")
    ]

    result = await service.handle_history_command(user, "/history 01.03.26 05.07.26")

    assert "20 Jun 2026 → 10 Jul 2026" in result.message
    assert "(16 days)" in result.message


@pytest.mark.asyncio
async def test_history_duration_full_containment(service: HistoryService) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-03-10", exit="2026-03-12", code="ID", name="Indonesia")
    ]

    result = await service.handle_history_command(user, "/history 01.03.26 05.07.26")

    assert "(3 days)" in result.message


@pytest.mark.asyncio
async def test_history_duration_active_stay_with_custom_range(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [_stay(1, entry="2026-05-17")]

    result = await service.handle_history_command(user, "/history 01.06.26 30.06.26")

    assert "17 May 2026 → Present" in result.message
    # today = May 30, window = Jun 1–Jun 30; stay capped to May 30 has no overlap → 0 days
    assert "(0 days)" in result.message


@pytest.mark.asyncio
async def test_history_duration_current_year_uses_year_overlap(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2025-12-25", exit="2026-01-10", code="ID", name="Indonesia")
    ]

    result = await service.handle_history_command(user, "/history 2026")

    assert "25 Dec 2025 → 10 Jan 2026" in result.message
    assert "(10 days)" in result.message


@pytest.mark.asyncio
async def test_history_duration_country_year_boundary_crossing(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2025-12-25", exit="2026-01-10", code="ID", name="Indonesia"),
        _stay(2, entry="2026-02-01", exit="2026-02-05"),
    ]

    result = await service.handle_history_command(user, "/history Indonesia 2026")

    assert "Indonesia" in result.message
    assert "Thailand" not in result.message
    assert "(10 days)" in result.message


@pytest.mark.asyncio
async def test_history_duration_inclusive_counting_correctness(
    service: HistoryService,
) -> None:
    user = _user()
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-03-01", exit="2026-03-01", code="ID", name="Indonesia")
    ]

    result = await service.handle_history_command(user, "/history 01.03.26 01.03.26")

    assert "(1 day)" in result.message


@pytest.mark.asyncio
async def test_history_custom_dates_handler_clears_fsm_after_valid_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    message = SimpleNamespace(
        from_user=SimpleNamespace(
            id=user.telegram_id, username="tester", first_name="Test"
        ),
        text="01.03.26 05.07.26",
        answer=AsyncMock(),
    )
    state = SimpleNamespace(
        clear=AsyncMock(),
        get_data=AsyncMock(return_value={"history_base_filter_key": "cTH"}),
    )

    class FakeUserService:
        def __init__(self, session: object) -> None:
            pass

        async def get_or_create(
            self, *args: object, **kwargs: object
        ) -> tuple[User, bool]:
            return user, False

    class FakeHistoryService:
        def __init__(self, session: object) -> None:
            pass

        async def handle_custom_date_range(
            self,
            user: User,
            text: str,
            *,
            base_filter_key: str | None = None,
        ) -> MessageResult:
            assert base_filter_key == "cTH"
            return MessageResult(message="history", keyboard=MagicMock())

    monkeypatch.setattr(history_handler, "UserService", FakeUserService)
    monkeypatch.setattr(history_handler, "HistoryService", FakeHistoryService)

    await history_handler.history_custom_dates(message, state, AsyncMock())

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_history_custom_dates_handler_keeps_fsm_after_invalid_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    message = SimpleNamespace(
        from_user=SimpleNamespace(
            id=user.telegram_id, username="tester", first_name="Test"
        ),
        text="bad range",
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock(), get_data=AsyncMock(return_value={}))

    class FakeUserService:
        def __init__(self, session: object) -> None:
            pass

        async def get_or_create(
            self, *args: object, **kwargs: object
        ) -> tuple[User, bool]:
            return user, False

    class FakeHistoryService:
        def __init__(self, session: object) -> None:
            pass

        async def handle_custom_date_range(
            self,
            user: User,
            text: str,
            *,
            base_filter_key: str | None = None,
        ) -> MessageResult:
            return MessageResult(message="error")

    monkeypatch.setattr(history_handler, "UserService", FakeUserService)
    monkeypatch.setattr(history_handler, "HistoryService", FakeHistoryService)

    await history_handler.history_custom_dates(message, state, AsyncMock())

    state.clear.assert_not_called()
    message.answer.assert_awaited_once_with("error", reply_markup=None)


@pytest.mark.asyncio
async def test_history_custom_dates_cancel_handler_clears_fsm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _user()
    message = SimpleNamespace(
        from_user=SimpleNamespace(
            id=user.telegram_id, username="tester", first_name="Test"
        ),
        answer=AsyncMock(),
    )
    state = SimpleNamespace(clear=AsyncMock())

    class FakeUserService:
        def __init__(self, session: object) -> None:
            pass

        async def get_or_create(
            self, *args: object, **kwargs: object
        ) -> tuple[User, bool]:
            return user, False

    class FakeHistoryService:
        def __init__(self, session: object) -> None:
            pass

        def cancel_custom_dates(self, user: User) -> MessageResult:
            return MessageResult(message="cancelled")

    monkeypatch.setattr(history_handler, "UserService", FakeUserService)
    monkeypatch.setattr(history_handler, "HistoryService", FakeHistoryService)

    await history_handler.cancel_history_custom_dates(message, state, AsyncMock())

    state.clear.assert_awaited_once()
    message.answer.assert_awaited_once_with("cancelled")


@pytest.mark.asyncio
async def test_where_threshold_indicator_in_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.handlers.where_command as where_handler

    user = _user()
    message = SimpleNamespace(
        from_user=SimpleNamespace(
            id=user.telegram_id,
            username=user.username,
            first_name=user.first_name,
        ),
        answer=AsyncMock(),
    )
    session = AsyncMock()

    class FakeUserService:
        def __init__(self, session: object) -> None:
            pass

        async def get_or_create(
            self, *args: object, **kwargs: object
        ) -> tuple[User, bool]:
            return user, False

    class FakeHistoryService:
        def __init__(self, session: object) -> None:
            pass

        async def handle_where_command(self, user: User) -> MessageResult:
            return MessageResult(
                message=(
                    "‍📍 Current active stay\n\n"
                    "\U0001f1f9\U0001f1ed Thailand\nEntered on 17 May 2026\n\n"
                    "Current stay:\n14 days\n\n"
                    "2026 totals:\n"
                    "• Calendar year: 97 days\n"
                    "• Rolling 365: 121 days\n\n"
                    "Remaining before 183-day calendar year threshold:\n"
                    "\U0001f7e2 86 days\n\n"
                    "Remaining before 183-day rolling window threshold:\n"
                    "\U0001f7e2 62 days"
                )
            )

    monkeypatch.setattr(where_handler, "UserService", FakeUserService)
    monkeypatch.setattr(where_handler, "HistoryService", FakeHistoryService)

    await where_handler.cmd_where(message, session)

    message.answer.assert_awaited_once()
    text = message.answer.call_args[0][0]
    assert "\U0001f7e2" in text
