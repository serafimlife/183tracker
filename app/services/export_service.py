"""CSV export of a user's complete travel history."""

import csv
import io
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stay import Stay
from app.repositories.stay_repository import StayRepository
from app.residency_engine.calculations import stay_duration_days


@dataclass(frozen=True, slots=True)
class ExportRow:
    country: str
    entry_date: date
    exit_date: date | None
    days: int


class ExportService:
    """Generate CSV export of travel history (newest-first)."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = StayRepository(session)

    async def generate_csv(self, telegram_id: int) -> str:
        stays = await self._repo.list_by_user(telegram_id)
        stays.sort(key=lambda stay: (stay.entry_date, stay.id or 0), reverse=True)

        today = date.today()
        rows = [_to_export_row(stay, today) for stay in stays]

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Country", "Entry Date", "Exit Date", "Days of Stay"])
        for row in rows:
            writer.writerow(
                [
                    row.country,
                    row.entry_date.isoformat(),
                    row.exit_date.isoformat() if row.exit_date is not None else "",
                    row.days,
                ]
            )
        return buf.getvalue()


def _to_export_row(stay: Stay, today: date) -> ExportRow:
    return ExportRow(
        country=stay.country_name,
        entry_date=stay.entry_date,
        exit_date=stay.exit_date,
        days=stay_duration_days(stay.entry_date, stay.exit_date, as_of=today),
    )
