"""Data access for `Stay`."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stay import Stay


class StayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, telegram_id: int) -> list[Stay]:
        result = await self._session.execute(
            select(Stay)
            .where(Stay.telegram_id == telegram_id)
            .order_by(Stay.entry_date, Stay.id)
        )
        return list(result.scalars().all())

    async def get_open_stay(
        self,
        telegram_id: int,
        country_code: str,
    ) -> Stay | None:
        result = await self._session.execute(
            select(Stay)
            .where(
                Stay.telegram_id == telegram_id,
                Stay.country_code == country_code,
                Stay.exit_date.is_(None),
            )
            .order_by(Stay.entry_date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_entry(
        self,
        telegram_id: int,
        *,
        country_code: str,
        country_name: str,
        entry_date: date,
    ) -> Stay:
        stay = Stay(
            telegram_id=telegram_id,
            country_code=country_code,
            country_name=country_name,
            entry_date=entry_date,
        )
        self._session.add(stay)
        await self._session.flush()
        return stay

    async def close_stay(self, stay: Stay, exit_date: date) -> Stay:
        stay.exit_date = exit_date
        await self._session.flush()
        return stay

    async def get_by_id(self, stay_id: int) -> Stay | None:
        result = await self._session.execute(select(Stay).where(Stay.id == stay_id))
        return result.scalar_one_or_none()

    async def delete(self, stay: Stay) -> None:
        await self._session.delete(stay)
        await self._session.flush()
