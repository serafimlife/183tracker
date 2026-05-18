"""`/in` command — record country entry with validated ISO code."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.stay_transition import StayTransitionStates
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandTransition,
    StayService,
)
from app.services.user_service import UserService

router = Router(name="in")


@router.message(Command("in"))
async def cmd_in(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None or message.text is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    result = await StayService(session).handle_in_command(user, message.text)

    if isinstance(result, StayCommandTransition):
        await state.set_state(StayTransitionStates.confirming)
        await state.update_data(**result.fsm_data)
        await message.answer(result.message, reply_markup=result.keyboard)
    elif isinstance(result, StayCommandConflict):
        await state.clear()
        await message.answer(result.message, reply_markup=result.keyboard)
    else:
        await state.clear()
        await message.answer(result.message)
