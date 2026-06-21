"""`/out` command — close an open stay."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.out_command import OutCommandStates
from app.services.localization_service import LocalizationService
from app.services.parsing_service import ParsingService
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandSuccess,
    StayService,
)
from app.services.user_service import UserService
from app.utils.countries import resolve_country
from app.utils.dates import parse_entry_date

router = Router(name="out")


async def _dispatch_global_command(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> bool:
    text = (message.text or "").strip()
    if not text.startswith("/"):
        return False
    token = text.split(maxsplit=1)[0].lower()
    command = token[1:].split("@", 1)[0]

    from app.handlers.history_command import cmd_history
    from app.handlers.in_command import cmd_in
    from app.handlers.report import cmd_report
    from app.handlers.settings import cmd_settings
    from app.handlers.start import cmd_start
    from app.handlers.where_command import cmd_where

    if command == "in":
        await cmd_in(message, state, session)
        return True
    if command == "out":
        await cmd_out(message, state, session)
        return True
    if command == "settings":
        await cmd_settings(message, session)
        return True
    if command == "where":
        await cmd_where(message, session)
        return True
    if command == "history":
        await cmd_history(message, session)
        return True
    if command == "report":
        await cmd_report(message, session)
        return True
    if command == "start":
        await cmd_start(message, state, session)
        return True
    return False


def _t(i18n: LocalizationService, key: str, default: str, **kwargs: str) -> str:
    try:
        return i18n.t(key, **kwargs)
    except KeyError:
        return default.format(**kwargs) if kwargs else default


async def _send_out_result(message: Message, state: FSMContext, result) -> None:
    if isinstance(result, StayCommandConflict):
        await state.clear()
        await message.answer(result.message, reply_markup=result.keyboard)
        return
    await state.clear()
    await message.answer(result.message)


@router.message(Command("out"))
async def cmd_out(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if message.from_user is None or message.text is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    i18n = LocalizationService(user.language or "en")
    body = ParsingService.extract_out_command_body(message.text)
    if body is None:
        return

    if user.is_onboarded and not body:
        await state.set_state(OutCommandStates.awaiting_country)
        await message.answer(
            _t(
                i18n,
                "out.prompt_country",
                "Which country do you want to add exit for?",
            )
        )
        return

    if user.is_onboarded and body:
        parsed = ParsingService.parse_out_command(message.text)
        if parsed is None:
            await state.set_state(OutCommandStates.awaiting_date)
            await state.update_data(out_pending_country=body)
            await message.answer(
                _t(
                    i18n,
                    "out.prompt_date_for_country",
                    "What is the exit date for {country}?\n\nExamples:\n- today\n- yesterday\n- 24.05.26",
                    country=body,
                )
            )
            return
        if (
            parse_entry_date(parsed.date_str, date_format=user.date_format) is None
            and resolve_country(body) is not None
        ):
            await state.set_state(OutCommandStates.awaiting_date)
            await state.update_data(out_pending_country=body)
            await message.answer(
                _t(
                    i18n,
                    "out.prompt_date_for_country",
                    "What is the exit date for {country}?\n\nExamples:\n- today\n- yesterday\n- 24.05.26",
                    country=body,
                )
            )
            return

    result = await StayService(session).handle_out_command(user, message.text)
    await _send_out_result(message, state, result)


@router.message(OutCommandStates.awaiting_country)
async def out_waiting_country(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None or message.text is None:
        return
    if message.text.strip().startswith("/"):
        await state.clear()
        if await _dispatch_global_command(message, state, session):
            return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    i18n = LocalizationService(user.language or "en")

    country_input = message.text.strip()
    country = resolve_country(country_input)
    if country is None:
        await message.answer(i18n.t("in.country_not_recognized"))
        return

    await state.set_state(OutCommandStates.awaiting_date)
    await state.update_data(out_pending_country=country["name"])
    await message.answer(
        _t(
            i18n,
            "out.prompt_date",
            "What is the exit date?\n\nExamples:\n- today\n- yesterday\n- 24.05.26",
        )
    )


@router.message(OutCommandStates.awaiting_date)
async def out_waiting_date(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None or message.text is None:
        return
    if message.text.strip().startswith("/"):
        await state.clear()
        if await _dispatch_global_command(message, state, session):
            return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    fsm_data = await state.get_data()
    country = str(fsm_data.get("out_pending_country", "")).strip()
    date_str = message.text.strip()
    if not country:
        await state.clear()
        await message.answer("Please send /out again.")
        return

    result = await StayService(session).handle_out_command(
        user, f"/out {country} {date_str}"
    )
    if isinstance(result, StayCommandConflict):
        await _send_out_result(message, state, result)
        return
    if isinstance(result, StayCommandSuccess):
        await state.clear()
    await message.answer(result.message)
