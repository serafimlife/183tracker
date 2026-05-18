"""User-related business logic — orchestrates repositories."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.logger import get_logger
from app.models.user import User
from app.repositories.user_repository import UserRepository

logger = get_logger(__name__)


class UserService:
    """Register and load Telegram users."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def get_or_create(
        self,
        telegram_id: int,
        *,
        username: str | None,
        first_name: str | None,
    ) -> tuple[User, bool]:
        """Return user and whether the row was just created."""
        user = await self._repo.get_by_telegram_id(telegram_id)
        if user is not None:
            await self._repo.update_profile(
                user, username=username, first_name=first_name
            )
            return user, False

        user = await self._repo.create(
            telegram_id,
            username=username,
            first_name=first_name,
        )
        logger.info(
            "user_registered telegram_id=%s",
            telegram_id,
        )
        return user, True
