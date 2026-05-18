"""`/out` command — close an open stay."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.stay_service import StayCommandConflict, StayService
from app.services.user_service import UserService

router = Router(name="out")


@router.message(Command("out"))
async def cmd_out(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.text is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    result = await StayService(session).handle_out_command(user, message.text)
    if isinstance(result, StayCommandConflict):
        await message.answer(result.message, reply_markup=result.keyboard)
    else:
        await message.answer(result.message)
