"""`/report` command — residency aggregation report."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.report import ReportFilterCallback
from app.bot.states.report import ReportStates
from app.services.filters import parse_timeline_filter
from app.services.report_service import ReportService
from app.services.user_service import UserService

router = Router(name="report")


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
    from app.handlers.out_command import cmd_out
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


@router.message(Command("report"))
async def cmd_report(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    text = message.text or ""
    lowered = text.lower()
    if lowered.startswith("/report"):
        body = text[7:].strip()
    elif lowered.startswith("report"):
        body = text[6:].strip()
    else:
        return

    filter = parse_timeline_filter(body, date_format=user.date_format)

    result = await ReportService(session).handle_report_command(user, filter)
    await message.answer(result.message, reply_markup=result.keyboard)


@router.callback_query(ReportFilterCallback.filter())
async def on_report_filter(
    callback: CallbackQuery,
    callback_data: ReportFilterCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.from_user is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )

    result = await ReportService(session).handle_report_callback(
        user,
        callback_data.filter_key,
    )
    if callback.message is not None:
        if result.fsm_data is not None:
            await state.set_state(ReportStates.waiting_for_custom_range)
            await state.update_data(**result.fsm_data)
            await callback.message.answer(result.message)
        else:
            await callback.message.edit_text(
                result.message, reply_markup=result.keyboard
            )
    await callback.answer()


@router.message(ReportStates.waiting_for_custom_range, Command("cancel"))
async def cancel_report_custom_dates(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    result = ReportService(session).cancel_custom_dates(user)
    await state.clear()
    await message.answer(result.message)


@router.message(ReportStates.waiting_for_custom_range)
async def report_custom_dates(
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
    result = await ReportService(session).handle_custom_date_range(
        user,
        message.text,
        base_filter_key=fsm_data.get("report_base_filter_key"),
    )
    if result.keyboard is not None:
        await state.clear()
    await message.answer(result.message, reply_markup=result.keyboard)
