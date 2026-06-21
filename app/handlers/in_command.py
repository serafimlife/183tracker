"""`/in` command — record country entry with validated ISO code."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.in_command import InCommandStates
from app.bot.states.stay_transition import StayTransitionStates
from app.services.localization_service import LocalizationService
from app.services.parsing_service import ParsingService
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandHistoricalExitPrompt,
    StayCommandSuccess,
    StayCommandTransition,
    StayService,
)
from app.services.user_service import UserService
from app.utils.countries import resolve_country
from app.utils.dates import parse_entry_date

router = Router(name="in")


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
    from app.handlers.out_command import cmd_out
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


async def _send_in_result(
    message: Message,
    state: FSMContext,
    result,
    *,
    add_tip: bool = False,
    tip_country: str | None = None,
    tip_date: str | None = None,
) -> None:
    if isinstance(result, StayCommandTransition):
        await state.set_state(StayTransitionStates.confirming)
        await state.update_data(**result.fsm_data)
        await message.answer(result.message, reply_markup=result.keyboard)
        return
    if isinstance(result, StayCommandHistoricalExitPrompt):
        await state.set_state(StayTransitionStates.confirming_historical_exit)
        await state.update_data(**result.fsm_data)
        await message.answer(result.message, reply_markup=result.keyboard)
        return
    if isinstance(result, StayCommandConflict):
        await state.clear()
        await message.answer(result.message, reply_markup=result.keyboard)
        return

    await state.clear()
    await message.answer(result.message)
    if (
        add_tip
        and isinstance(result, StayCommandSuccess)
        and tip_country is not None
        and tip_date is not None
    ):
        await message.answer(
            f"Tip: you can also do this faster with:\n\n/in {tip_country} {tip_date}"
        )


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

    i18n = LocalizationService(user.language or "en")
    body = ParsingService.extract_in_command_body(message.text)
    if body is None:
        return

    if user.is_onboarded and not body:
        await state.set_state(InCommandStates.awaiting_country)
        await message.answer(
            _t(
                i18n,
                "in.prompt_country",
                "Which country do you want to add entry to?",
            )
        )
        return

    if user.is_onboarded and body:
        parsed = ParsingService.parse_in_command(message.text)
        if parsed is None:
            await state.set_state(InCommandStates.awaiting_date)
            await state.update_data(in_pending_country=body)
            await message.answer(
                _t(
                    i18n,
                    "in.prompt_date_for_country",
                    "What is the entry date for {country}?\n\nExamples:\n- today\n- yesterday\n- 24.05.26",
                    country=body,
                )
            )
            return
        if (
            parse_entry_date(parsed.date_str, date_format=user.date_format) is None
            and resolve_country(body) is not None
        ):
            await state.set_state(InCommandStates.awaiting_date)
            await state.update_data(in_pending_country=body)
            await message.answer(
                _t(
                    i18n,
                    "in.prompt_date_for_country",
                    "What is the entry date for {country}?\n\nExamples:\n- today\n- yesterday\n- 24.05.26",
                    country=body,
                )
            )
            return

    result = await StayService(session).handle_in_command(user, message.text)
    await _send_in_result(message, state, result)


@router.message(InCommandStates.awaiting_country)
async def in_waiting_country(
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

    await state.set_state(InCommandStates.awaiting_date)
    await state.update_data(in_pending_country=country["name"])
    await message.answer(
        _t(
            i18n,
            "in.prompt_date",
            "What is the entry date?\n\nExamples:\n- today\n- yesterday\n- 24.05.26",
        )
    )


@router.message(InCommandStates.awaiting_date)
async def in_waiting_date(
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
    country = str(fsm_data.get("in_pending_country", "")).strip()
    date_str = message.text.strip()
    if not country:
        await state.clear()
        await message.answer("Please send /in again.")
        return

    result = await StayService(session).handle_in_command(
        user, f"/in {country} {date_str}"
    )
    if isinstance(result, StayCommandSuccess):
        await _send_in_result(
            message,
            state,
            result,
            add_tip=True,
            tip_country=country,
            tip_date=date_str,
        )
        return

    if isinstance(
        result,
        StayCommandConflict | StayCommandTransition | StayCommandHistoricalExitPrompt,
    ):
        await _send_in_result(message, state, result)
        return

    await message.answer(result.message)
