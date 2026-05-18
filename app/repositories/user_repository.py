"""Data access for `User` — no business rules, only persistence."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """CRUD and queries for users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        telegram_id: int,
        *,
        username: str | None,
        first_name: str | None,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def update_profile(
        self,
        user: User,
        *,
        username: str | None,
        first_name: str | None,
    ) -> User:
        user.username = username
        user.first_name = first_name
        await self._session.flush()
        return user

    async def set_language(self, user: User, language: str) -> User:
        user.language = language
        await self._session.flush()
        return user

    async def set_date_format(self, user: User, date_format: str) -> User:
        user.date_format = date_format
        await self._session.flush()
        return user
