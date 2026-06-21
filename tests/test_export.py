"""Tests for /export CSV generation."""

import csv
import io
from datetime import date
from unittest.mock import AsyncMock

import pytest

import app.services.export_service as export_module
from app.models.stay import Stay
from app.services.export_service import ExportService


class FixedDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2026, 5, 30)


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


def _parse_csv(content: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(content))
    return list(reader)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_module, "date", FixedDate)


@pytest.fixture
def service() -> ExportService:
    session = AsyncMock()
    svc = ExportService(session)
    svc._repo = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_csv_headers(service: ExportService) -> None:
    service._repo.list_by_user.return_value = []

    csv_content = await service.generate_csv(100)

    reader = csv.DictReader(io.StringIO(csv_content))
    assert reader.fieldnames == ["Country", "Entry Date", "Exit Date", "Days of Stay"]


@pytest.mark.asyncio
async def test_csv_row_formatting(service: ExportService) -> None:
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-03-10", exit="2026-03-12", code="ID", name="Indonesia"),
    ]

    csv_content = await service.generate_csv(100)
    rows = _parse_csv(csv_content)

    assert len(rows) == 1
    assert rows[0]["Country"] == "Indonesia"
    assert rows[0]["Entry Date"] == "2026-03-10"
    assert rows[0]["Exit Date"] == "2026-03-12"
    assert rows[0]["Days of Stay"] == "3"


@pytest.mark.asyncio
async def test_ordering_newest_first(service: ExportService) -> None:
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-01-01", exit="2026-01-02"),
        _stay(2, entry="2026-05-01", exit="2026-05-02", code="ID", name="Indonesia"),
    ]

    csv_content = await service.generate_csv(100)
    rows = _parse_csv(csv_content)

    assert rows[0]["Country"] == "Indonesia"
    assert rows[1]["Country"] == "Thailand"


@pytest.mark.asyncio
async def test_active_stay_empty_exit_date(service: ExportService) -> None:
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-05-17"),
    ]

    csv_content = await service.generate_csv(100)
    rows = _parse_csv(csv_content)

    assert rows[0]["Exit Date"] == ""
    assert rows[0]["Days of Stay"] == "14"  # 2026-05-17 to 2026-05-30 inclusive


@pytest.mark.asyncio
async def test_inclusive_counting(service: ExportService) -> None:
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-03-01", exit="2026-03-01", code="ID", name="Indonesia"),
    ]

    csv_content = await service.generate_csv(100)
    rows = _parse_csv(csv_content)

    assert rows[0]["Days of Stay"] == "1"


@pytest.mark.asyncio
async def test_empty_history(service: ExportService) -> None:
    service._repo.list_by_user.return_value = []

    csv_content = await service.generate_csv(100)

    rows = _parse_csv(csv_content)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_multiple_stays_with_mixed_active(service: ExportService) -> None:
    service._repo.list_by_user.return_value = [
        _stay(1, entry="2026-01-01", exit="2026-01-05"),
        _stay(2, entry="2026-05-17"),
        _stay(3, entry="2026-03-10", exit="2026-03-12", code="ID", name="Indonesia"),
    ]

    csv_content = await service.generate_csv(100)
    rows = _parse_csv(csv_content)

    assert len(rows) == 3
    # Newest first: May 17, Mar 10-12, Jan 1-5
    assert rows[0]["Country"] == "Thailand"
    assert rows[0]["Entry Date"] == "2026-05-17"
    assert rows[0]["Exit Date"] == ""
    assert rows[0]["Days of Stay"] == "14"

    assert rows[1]["Country"] == "Indonesia"
    assert rows[1]["Days of Stay"] == "3"

    assert rows[2]["Country"] == "Thailand"
    assert rows[2]["Days of Stay"] == "5"
