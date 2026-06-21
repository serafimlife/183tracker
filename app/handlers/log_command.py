"""`/log` command — create a completed stay."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.log_command import LogCommandStates
from app.services.parsing_service import ParsingService
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandSuccess,
    StayService,
)
from app.services.user_service import UserService

router = Router(name="log")


async def _get_user(message: Message, session: AsyncSession):
    if message.from_user is None:
        return None
    user, _ = await UserService(session).get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    return user


async def _send_result(message: Message, state: FSMContext, result) -> None:
    if isinstance(result, StayCommandConflict):
        await state.clear()
        await message.answer(result.message, reply_markup=result.keyboard)
        return
    if isinstance(result, StayCommandSuccess):
        await state.clear()
    await message.answer(result.message)


@router.message(Command("log"))
async def cmd_log(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.text is None:
        return

    body = ParsingService.extract_log_command_body(message.text)
    if body is None:
        return
    if not body:
        await state.set_state(LogCommandStates.awaiting_country)
        await message.answer("Which country did you stay in?")
        return

    user = await _get_user(message, session)
    if user is None:
        return
    result = await StayService(session).handle_log_command(user, message.text)
    await _send_result(message, state, result)


@router.message(LogCommandStates.awaiting_country)
async def log_waiting_country(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    await state.update_data(log_country=message.text.strip())
    await state.set_state(LogCommandStates.awaiting_entry_date)
    await message.answer("What was the entry date?")


@router.message(LogCommandStates.awaiting_entry_date)
async def log_waiting_entry_date(message: Message, state: FSMContext) -> None:
    if message.text is None:
        return
    await state.update_data(log_entry_date=message.text.strip())
    await state.set_state(LogCommandStates.awaiting_exit_date)
    await message.answer("What was the exit date?")


@router.message(LogCommandStates.awaiting_exit_date)
async def log_waiting_exit_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.text is None:
        return

    data = await state.get_data()
    country = str(data.get("log_country", "")).strip()
    entry_date = str(data.get("log_entry_date", "")).strip()
    if not country or not entry_date:
        await state.clear()
        await message.answer("Please send /log again.")
        return

    user = await _get_user(message, session)
    if user is None:
        return
    result = await StayService(session).handle_log_command(
        user,
        f"/log {country} {entry_date} {message.text.strip()}",
    )
    await _send_result(message, state, result)
