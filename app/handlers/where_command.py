"""`/where` command — show current active stay and totals."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.history_service import HistoryService
from app.services.user_service import UserService

router = Router(name="where")


@router.message(Command("where"))
async def cmd_where(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    result = await HistoryService(session).handle_where_command(user)

    await message.answer(result.message, reply_markup=result.keyboard)
