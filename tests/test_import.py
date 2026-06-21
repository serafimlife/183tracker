"""Tests for CSV import service."""

import io
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from openpyxl import Workbook

from app.bot.states.import_data import ImportStates
from app.handlers import import_command
from app.models.stay import Stay
from app.services.import_service import ImportResult, ImportService


def _stay(
    entry: str, exit: str | None = None, code: str = "TH", name: str = "Thailand"
) -> Stay:
    s = Stay()
    s.id = 1
    s.telegram_id = 100
    s.country_code = code
    s.country_name = name
    s.entry_date = date.fromisoformat(entry)
    s.exit_date = date.fromisoformat(exit) if exit else None
    return s


CSV_VALID = """\
Country,Date of entry,Date of exit
Thailand,2026-01-01,2026-02-15
Indonesia,2026-02-15,2026-05-01
"""


@pytest.fixture
def service() -> ImportService:
    session = AsyncMock()
    svc = ImportService(session)
    svc._repo = AsyncMock()
    return svc


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


def _document_message(filename: str, file_id: str = "file-id", file_size: int = 1000):
    return SimpleNamespace(
        document=SimpleNamespace(
            file_name=filename, file_id=file_id, file_size=file_size
        ),
        from_user=SimpleNamespace(id=100),
        bot=SimpleNamespace(),
        answer=AsyncMock(),
    )


def _callback(value: str):
    return SimpleNamespace(
        message=SimpleNamespace(answer=AsyncMock()),
        from_user=SimpleNamespace(id=100),
        answer=AsyncMock(),
    ), import_command.ImportDateFormatCallback(value=value)


@pytest.mark.asyncio
async def test_csv_with_headers(service: ImportService) -> None:
    service._repo.list_by_user.return_value = []

    def _create_entry(telegram_id, *, country_code, country_name, entry_date):
        s = _stay(entry=entry_date.isoformat(), code=country_code, name=country_name)
        s.id = 1
        return s

    service._repo.create_entry.side_effect = _create_entry

    result = await service.import_csv(100, CSV_VALID)

    assert result.added_entries == 2
    assert len(result.countries) == 2
    assert result.total_days > 0
    assert len(result.errors) == 0
    assert "2 entries added" in result.message
    assert "2 countries" in result.message


@pytest.mark.asyncio
async def test_csv_without_headers(service: ImportService) -> None:
    service._repo.list_by_user.return_value = []
    service._repo.create_entry.side_effect = lambda tid, **kw: _stay(
        entry=kw["entry_date"].isoformat(),
        code=kw["country_code"],
        name=kw["country_name"],
    )

    csv = """\
Thailand,01.01.26,15.02.26
Japan,16.02.26,20.03.26
"""

    result = await service.import_csv(100, csv, date_format="%d.%m.%y")

    assert result.added_entries == 2
    assert result.errors == []


@pytest.mark.asyncio
async def test_invalid_country(service: ImportService) -> None:
    service._repo.list_by_user.return_value = []

    csv = """\
Country,Date of entry,Date of exit
Thailannd,2026-01-01,2026-02-15
"""

    result = await service.import_csv(100, csv)

    assert result.added_entries == 0
    assert len(result.errors) == 1
    assert "unknown country" in result.errors[0].message


@pytest.mark.asyncio
async def test_invalid_date(service: ImportService) -> None:
    service._repo.list_by_user.return_value = []

    csv = """\
Country,Date of entry,Date of exit
Thailand,not-a-date,2026-02-15
"""

    result = await service.import_csv(100, csv)

    assert result.added_entries == 0
    assert len(result.errors) == 1
    assert "invalid dates" in result.errors[0].message


@pytest.mark.asyncio
async def test_overlap_conflict(service: ImportService) -> None:
    existing = [_stay(entry="2026-01-01", exit="2026-03-01")]
    service._repo.list_by_user.return_value = existing
    service._repo.create_entry.side_effect = lambda tid, **kw: _stay(
        entry=kw["entry_date"].isoformat(),
        code=kw["country_code"],
        name=kw["country_name"],
    )

    csv = """\
Country,Date of entry,Date of exit
Thailand,2026-02-01,2026-04-01
"""

    result = await service.import_csv(100, csv)

    assert result.added_entries == 0
    assert len(result.errors) == 1
    assert "overlaps" in result.errors[0].message


@pytest.mark.asyncio
async def test_partial_import(service: ImportService) -> None:
    service._repo.list_by_user.return_value = []
    service._repo.create_entry.side_effect = lambda tid, **kw: _stay(
        entry=kw["entry_date"].isoformat(),
        code=kw["country_code"],
        name=kw["country_name"],
    )

    csv = """\
Country,Date of entry,Date of exit
Thailand,2026-01-01,2026-02-15
BadLand,2026-03-01,2026-04-01
Indonesia,not-a-date,2026-05-01
Spain,2026-06-01,2026-07-01
"""

    result = await service.import_csv(100, csv)

    assert result.added_entries == 2
    assert len(result.errors) == 2
    assert "Skipped rows" in result.message


@pytest.mark.asyncio
async def test_csv_ignores_trailing_empty_and_unrelated_columns(
    service: ImportService,
) -> None:
    service._repo.list_by_user.return_value = []
    service._repo.create_entry.side_effect = lambda tid, **kw: _stay(
        entry=kw["entry_date"].isoformat(),
        code=kw["country_code"],
        name=kw["country_name"],
    )

    csv = """\
Notes,Departure,Country,Arrival,,,,,
ignore,15.02.2026,Thailand,01.01.2026,,,,,
"""

    result = await service.import_csv(100, csv, date_format="%d.%m.%Y")

    assert result.added_entries == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_xlsx_with_headers(service: ImportService) -> None:
    service._repo.list_by_user.return_value = []
    service._repo.create_entry.side_effect = lambda tid, **kw: _stay(
        entry=kw["entry_date"].isoformat(),
        code=kw["country_code"],
        name=kw["country_name"],
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Country", "Arrival", "Departure"])
    sheet.append(["Thailand", "01.01.26", "15.02.26"])
    content = io.BytesIO()
    workbook.save(content)

    result = await service.import_xlsx(
        100,
        content.getvalue(),
        date_format="%d.%m.%y",
    )

    assert result.added_entries == 1
    assert result.errors == []


@pytest.mark.asyncio
async def test_xlsx_without_headers(service: ImportService) -> None:
    service._repo.list_by_user.return_value = []
    service._repo.create_entry.side_effect = lambda tid, **kw: _stay(
        entry=kw["entry_date"].isoformat(),
        code=kw["country_code"],
        name=kw["country_name"],
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.append([None, None, None])
    sheet.append(["Thailand", "01.01.26", "15.02.26", "ignored"])
    sheet.append([None, None, None])
    sheet.append(["Japan", "16.02.26", "20.03.26", None])
    content = io.BytesIO()
    workbook.save(content)

    result = await service.import_xlsx(
        100,
        content.getvalue(),
        date_format="%d.%m.%y",
    )

    assert result.added_entries == 2
    assert result.errors == []


@pytest.mark.asyncio
async def test_blank_rows_before_and_between_positional_data(
    service: ImportService,
) -> None:
    service._repo.list_by_user.return_value = []
    service._repo.create_entry.side_effect = lambda tid, **kw: _stay(
        entry=kw["entry_date"].isoformat(),
        code=kw["country_code"],
        name=kw["country_name"],
    )

    csv = """\
,,,

Thailand,01.01.26,15.02.26
,,
Japan,16.02.26,20.03.26
"""

    result = await service.import_csv(100, csv, date_format="%d.%m.%y")

    assert result.added_entries == 2
    assert result.errors == []


@pytest.mark.asyncio
async def test_import_starts_with_date_format_selection() -> None:
    state = FakeState()
    message = SimpleNamespace(answer=AsyncMock())

    await import_command.cmd_import(message, state)

    assert state.current == ImportStates.awaiting_date_format
    message.answer.assert_awaited_once()
    assert (
        message.answer.await_args.args[0] == "Choose the date format used in your file:"
    )
    keyboard = message.answer.await_args.kwargs["reply_markup"]
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert button_texts == [
        "01.03.2026 (DD.MM.YYYY)",
        "01.03.26 (DD.MM.YY)",
        "2026-03-01 (YYYY-MM-DD)",
        "03/01/2026 (MM/DD/YYYY)",
        "More formats",
    ]


@pytest.mark.asyncio
async def test_standard_format_selection_prompts_for_upload() -> None:
    state = FakeState()
    callback, callback_data = _callback("dmy_long")

    await import_command.on_import_date_format(callback, callback_data, state)

    assert state.current == ImportStates.awaiting_file
    assert state.data["import_date_format"] == "%d.%m.%Y"
    callback.message.answer.assert_awaited_once_with(
        "Now upload your CSV or XLSX file."
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_more_formats_shows_second_menu() -> None:
    state = FakeState()
    await state.set_state(ImportStates.awaiting_date_format)
    callback, callback_data = _callback("more")

    await import_command.on_import_date_format(callback, callback_data, state)

    assert state.current == ImportStates.awaiting_date_format
    callback.message.answer.assert_awaited_once()
    assert (
        callback.message.answer.await_args.args[0]
        == "Choose the date format used in your file:"
    )
    keyboard = callback.message.answer.await_args.kwargs["reply_markup"]
    button_texts = [row[0].text for row in keyboard.inline_keyboard]
    assert button_texts == [
        "01/03/2026 (DD/MM/YYYY)",
        "01-03-2026 (DD-MM-YYYY)",
        "2026/03/01 (YYYY/MM/DD)",
        "01 Mar 2026",
        "Back",
    ]
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_more_format_selection_prompts_for_upload() -> None:
    state = FakeState()
    callback, callback_data = _callback("dmy_dash")

    await import_command.on_import_date_format(callback, callback_data, state)

    assert state.current == ImportStates.awaiting_file
    assert state.data["import_date_format"] == "%d-%m-%Y"
    callback.message.answer.assert_awaited_once_with(
        "Now upload your CSV or XLSX file."
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_more_formats_back_returns_to_initial_menu() -> None:
    state = FakeState()
    await state.set_state(ImportStates.awaiting_date_format)
    callback, callback_data = _callback("back")

    await import_command.on_import_date_format(callback, callback_data, state)

    assert state.current == ImportStates.awaiting_date_format
    callback.message.answer.assert_awaited_once()
    assert (
        callback.message.answer.await_args.args[0]
        == "Choose the date format used in your file:"
    )
    keyboard = callback.message.answer.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[-1][0].text == "More formats"
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_unsupported_then_supported_file_keeps_import_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_import_csv(self, telegram_id, csv_text, *, date_format):
        assert date_format == "%Y-%m-%d"
        return ImportResult(added_entries=1)

    monkeypatch.setattr(ImportService, "import_csv", fake_import_csv)

    state = FakeState()
    await state.set_state(ImportStates.awaiting_file)
    await state.update_data(import_date_format="%Y-%m-%d")

    unsupported = _document_message("travel.txt")
    await import_command.handle_import_file(unsupported, state, session=AsyncMock())

    assert state.current == ImportStates.awaiting_file
    unsupported.answer.assert_awaited_once_with(
        "Unsupported file type. Please upload a CSV or XLSX file."
    )

    supported = _document_message("travel.csv")
    supported.bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="travel.csv")),
        download_file=AsyncMock(
            return_value=io.BytesIO(
                b"Country,Date of entry,Date of exit\nThailand,2026-01-01,2026-02-15\n"
            )
        ),
    )
    await import_command.handle_import_file(supported, state, session=AsyncMock())

    assert state.current is None
    supported.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_after_format_selection_imports_with_selected_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_import_csv(self, telegram_id, csv_text, *, date_format):
        captured["date_format"] = date_format
        captured["csv_text"] = csv_text
        return ImportResult(added_entries=1)

    monkeypatch.setattr(ImportService, "import_csv", fake_import_csv)

    state = FakeState()
    await state.update_data(import_date_format="%d.%m.%Y")
    await state.set_state(ImportStates.awaiting_file)

    message = _document_message("travel.csv")
    message.bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="travel.csv")),
        download_file=AsyncMock(
            return_value=io.BytesIO(
                b"Country,Arrival,Departure\nThailand,01.01.2026,15.02.2026\n"
            )
        ),
    )

    await import_command.handle_import_file(
        message,
        state,
        session=AsyncMock(),
    )

    assert captured["date_format"] == "%d.%m.%Y"
    assert "01.01.2026" in captured["csv_text"]
    assert state.current is None
    message.answer.assert_awaited_once()
