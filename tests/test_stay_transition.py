"""Tests for guided country transition flow."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.models.stay import Stay
from app.models.user import User
from app.services.stay_service import (
    FSM_CLOSE_STAY_ID,
    FSM_ENTRY_DATE,
    FSM_HISTORICAL_EXIT_DATE,
    FSM_HISTORICAL_STAY_ID,
    FSM_NEW_COUNTRY_CODE,
    FSM_NEW_COUNTRY_NAME,
    StayCommandConflict,
    StayCommandHistoricalExitPrompt,
    StayCommandSuccess,
    StayCommandTransition,
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
    entry: str = "2026-02-25",
    exit: str | None = None,
    code: str = "ID",
    name: str = "Indonesia",
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
async def test_active_stay_transition_prompt(service: StayService) -> None:
    user = _user()
    indonesia = _stay(
        1, user.telegram_id, entry="2026-02-25", code="ID", name="Indonesia"
    )
    service._repo.list_by_user.return_value = [indonesia]

    result = await service.handle_in_command(user, "/in Thailand today")

    assert isinstance(result, StayCommandTransition)
    assert result.fsm_data[FSM_CLOSE_STAY_ID] == 1
    assert result.fsm_data[FSM_NEW_COUNTRY_CODE] == "TH"
    assert "tr_yes" in result.keyboard.inline_keyboard[0][0].callback_data
    service._repo.create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_live_transition_still_prompts_after_active_entry(
    service: StayService,
) -> None:
    user = _user()
    thailand = _stay(
        1,
        user.telegram_id,
        entry="2026-05-17",
        code="TH",
        name="Thailand",
    )
    service._repo.list_by_user.return_value = [thailand]

    result = await service.handle_in_command(user, "/in Indonesia 18.05.26")

    assert isinstance(result, StayCommandTransition)
    assert result.fsm_data[FSM_CLOSE_STAY_ID] == 1
    assert result.fsm_data[FSM_NEW_COUNTRY_CODE] == "ID"
    service._repo.create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_historical_insertion_with_future_stay_prompts_for_exit(
    service: StayService,
) -> None:
    user = _user()
    thailand = _stay(
        1,
        user.telegram_id,
        entry="2026-05-17",
        code="TH",
        name="Thailand",
    )
    indonesia = _stay(
        2,
        user.telegram_id,
        entry="2026-02-25",
        code="ID",
        name="Indonesia",
    )
    service._repo.list_by_user.return_value = [thailand]
    service._repo.create_entry.return_value = indonesia

    result = await service.handle_in_command(user, "/in Indonesia 25.02.26")

    assert isinstance(result, StayCommandHistoricalExitPrompt)
    assert result.fsm_data[FSM_HISTORICAL_STAY_ID] == 2
    assert result.fsm_data[FSM_HISTORICAL_EXIT_DATE] == "2026-05-17"
    assert "Indonesia was added starting on 25 February 2026" in result.message
    assert "Thailand on 17 May 2026" in result.message
    buttons = result.keyboard.inline_keyboard
    assert buttons[0][0].text == "Yes, 17 May"
    assert "hx_yes" in buttons[0][0].callback_data
    assert buttons[1][0].text == "Another Date"
    assert "hx_other" in buttons[1][0].callback_data
    assert buttons[1][1].text == "Keep Open"
    assert "hx_open" in buttons[1][1].callback_data
    service._repo.create_entry.assert_awaited_once_with(
        user.telegram_id,
        country_code="ID",
        country_name="Indonesia",
        entry_date=date(2026, 2, 25),
    )


@pytest.mark.asyncio
async def test_historical_insertion_without_future_stay_creates_normally(
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
    service._repo.list_by_user.return_value = []
    service._repo.create_entry.return_value = indonesia

    result = await service.handle_in_command(user, "/in Indonesia 25.02.26")

    assert isinstance(result, StayCommandSuccess)
    assert "Entered 🇮🇩 Indonesia" in result.message


@pytest.mark.asyncio
async def test_historical_insertion_still_rejects_real_overlap(
    service: StayService,
) -> None:
    user = _user()
    closed_indonesia = _stay(
        1,
        user.telegram_id,
        entry="2026-05-01",
        exit="2026-05-20",
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
    service._repo.list_by_user.return_value = [closed_indonesia, thailand]

    result = await service.handle_in_command(user, "/in Malaysia 02.05.26")

    assert isinstance(result, StayCommandConflict)
    assert "conflicts with an existing stay" in result.message
    service._repo.create_entry.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_historical_exit_closes_on_next_entry_and_recalculates_totals(
    service: StayService,
) -> None:
    user = _user()
    indonesia = _stay(
        2,
        user.telegram_id,
        entry="2026-02-25",
        code="ID",
        name="Indonesia",
    )
    thailand = _stay(
        1,
        user.telegram_id,
        entry="2026-05-17",
        code="TH",
        name="Thailand",
    )
    service._repo.get_by_id.return_value = indonesia
    service._repo.list_by_user.return_value = [indonesia, thailand]
    fsm_data = {
        FSM_HISTORICAL_STAY_ID: 2,
        FSM_HISTORICAL_EXIT_DATE: "2026-05-17",
    }

    result = await service.confirm_historical_exit(user, 2, fsm_data)

    assert isinstance(result, StayCommandSuccess)
    service._repo.close_stay.assert_awaited_once_with(indonesia, date(2026, 5, 17))
    assert "Stay duration:\n82 days" in result.message
    assert "Calendar year: 82 days" in result.message


@pytest.mark.asyncio
async def test_keep_historical_stay_open_does_not_close(service: StayService) -> None:
    user = _user()
    indonesia = _stay(2, user.telegram_id, entry="2026-02-25")
    service._repo.get_by_id.return_value = indonesia
    fsm_data = {
        FSM_HISTORICAL_STAY_ID: 2,
        FSM_HISTORICAL_EXIT_DATE: "2026-05-17",
    }

    result = await service.keep_historical_stay_open(user, 2, fsm_data)

    assert isinstance(result, StayCommandSuccess)
    assert "will stay open" in result.message
    service._repo.close_stay.assert_not_called()


@pytest.mark.asyncio
async def test_another_historical_exit_date_waits_for_manual_out(
    service: StayService,
) -> None:
    user = _user()
    indonesia = _stay(2, user.telegram_id, entry="2026-02-25")
    service._repo.get_by_id.return_value = indonesia
    fsm_data = {
        FSM_HISTORICAL_STAY_ID: 2,
        FSM_HISTORICAL_EXIT_DATE: "2026-05-17",
    }

    result = await service.choose_another_historical_exit_date(user, 2, fsm_data)

    assert isinstance(result, StayCommandSuccess)
    assert "/out Indonesia date" in result.message
    service._repo.close_stay.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_transition_closes_and_creates(service: StayService) -> None:
    user = _user()
    indonesia = _stay(1, user.telegram_id, entry="2026-02-25", code="ID")
    thailand = _stay(
        2, user.telegram_id, entry="2026-05-17", code="TH", name="Thailand"
    )
    service._repo.get_by_id.return_value = indonesia
    service._repo.list_by_user.return_value = [indonesia]
    service._repo.create_entry.return_value = thailand

    fsm_data = {
        FSM_CLOSE_STAY_ID: 1,
        FSM_NEW_COUNTRY_CODE: "TH",
        FSM_NEW_COUNTRY_NAME: "Thailand",
        FSM_ENTRY_DATE: "2026-05-17",
    }
    result = await service.confirm_country_transition(user, 1, fsm_data)

    assert isinstance(result, StayCommandSuccess)
    service._repo.close_stay.assert_awaited_once()
    service._repo.create_entry.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_transition(service: StayService) -> None:
    user = _user()
    result = service.cancel_country_transition(user)
    assert isinstance(result, StayCommandSuccess)
    assert "cancelled" in result.message.lower()


@pytest.mark.asyncio
async def test_same_country_duplicate_not_transition(service: StayService) -> None:
    user = _user()
    thailand = _stay(
        1, user.telegram_id, entry="2026-05-17", code="TH", name="Thailand"
    )
    service._repo.list_by_user.return_value = [thailand]

    result = await service.handle_in_command(user, "/in Thailand 17.05.26")

    assert isinstance(result, StayCommandConflict)


@pytest.mark.asyncio
async def test_overlap_not_transition(service: StayService) -> None:
    user = _user()
    indonesia = _stay(
        1, user.telegram_id, entry="2026-01-01", exit="2026-01-30", code="ID"
    )
    service._repo.list_by_user.return_value = [indonesia]

    result = await service.handle_in_command(user, "/in Thailand 29.01.26")

    assert isinstance(result, StayCommandConflict)
    assert "rm_stay" in result.keyboard.inline_keyboard[0][0].callback_data
    service._repo.create_entry.assert_not_called()
