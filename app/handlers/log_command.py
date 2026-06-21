"""`/log` command — create a completed stay."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.log_command import LogCommandStates
from app.services.localization_service import LocalizationService
from app.services.parsing_service import ParsingService
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandError,
    StayCommandSuccess,
    StayService,
)
from app.services.user_service import UserService
from app.utils.dates import parse_entry_date

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
    if isinstance(result, (StayCommandSuccess, StayCommandError)):
        await state.clear()
    await message.answer(result.message)


async def _dispatch_global_command(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Clear FSM state and dispatch a global slash command."""
    await state.clear()
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return
    token = text.split(maxsplit=1)[0].lower()
    command = token[1:].split("@", 1)[0]

    if command == "log":
        await cmd_log(message, state, session)
        return

    from app.handlers.history_command import cmd_history
    from app.handlers.in_command import cmd_in
    from app.handlers.out_command import cmd_out
    from app.handlers.report import cmd_report
    from app.handlers.settings import cmd_settings
    from app.handlers.start import cmd_start
    from app.handlers.where_command import cmd_where

    if command == "in":
        await cmd_in(message, state, session)
    elif command == "out":
        await cmd_out(message, state, session)
    elif command == "settings":
        await cmd_settings(message, session)
    elif command == "where":
        await cmd_where(message, session)
    elif command == "history":
        await cmd_history(message, session)
    elif command == "report":
        await cmd_report(message, session)
    elif command == "start":
        await cmd_start(message, state, session)
    else:
        await message.answer("Cancelled.")


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
async def log_waiting_country(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.text is None:
        return
    if message.text.strip().startswith("/"):
        await _dispatch_global_command(message, state, session)
        return
    await state.update_data(log_country=message.text.strip())
    await state.set_state(LogCommandStates.awaiting_entry_date)
    await message.answer("What was the entry date?")


@router.message(LogCommandStates.awaiting_entry_date)
async def log_waiting_entry_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.text is None:
        return
    text = message.text.strip()
    if text.startswith("/"):
        await _dispatch_global_command(message, state, session)
        return
    user = await _get_user(message, session)
    if user is None:
        return
    parsed = parse_entry_date(text, date_format=user.date_format)
    if parsed is None:
        i18n = LocalizationService(user.language or "en")
        await message.answer(i18n.t("in.invalid_date"))
        return
    await state.update_data(log_entry_date=text)
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
    text = message.text.strip()
    if text.startswith("/"):
        await _dispatch_global_command(message, state, session)
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
        f"/log {country} {entry_date} {text}",
    )
    await _send_result(message, state, result)
