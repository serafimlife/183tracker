"""`/history` command and pagination callbacks."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.history import (
    HistoryPageCallback,
    ManageConfirmDeleteCallback,
    ManageDeleteCallback,
    ManageEditFieldCallback,
    ManageEditMenuCallback,
    ManageHistoryCallback,
    ManageSelectCallback,
)
from app.bot.states.history import HistoryManageStates, HistoryStates
from app.models.user import User
from app.services.history_service import HistoryService
from app.services.localization_service import LocalizationService
from app.services.stay_service import (
    StayCommandConflict,
    StayRemoveError,
    StayService,
    StayUpdateError,
)
from app.services.user_service import UserService

router = Router(name="history")


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

    from app.handlers.in_command import cmd_in
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


@router.message(Command("history"))
async def cmd_history(message: Message, session: AsyncSession) -> None:
    if message.from_user is None or message.text is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    result = await HistoryService(session).handle_history_command(user, message.text)
    await message.answer(result.message, reply_markup=result.keyboard)


@router.callback_query(HistoryPageCallback.filter())
async def on_history_page(
    callback: CallbackQuery,
    callback_data: HistoryPageCallback,
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

    result = await HistoryService(session).handle_history_callback(
        user,
        callback_data.filter_key,
        page=callback_data.page,
    )

    if callback.message is not None:
        if result.fsm_data is not None:
            await state.set_state(HistoryStates.waiting_for_custom_range)
            await state.update_data(**result.fsm_data)
            await callback.message.answer(result.message)
        else:
            await callback.message.edit_text(
                result.message, reply_markup=result.keyboard
            )
    await callback.answer()


@router.message(HistoryStates.waiting_for_custom_range, Command("cancel"))
async def cancel_history_custom_dates(
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

    result = HistoryService(session).cancel_custom_dates(user)
    await state.clear()
    await message.answer(result.message)


@router.message(HistoryStates.waiting_for_custom_range)
async def history_custom_dates(
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
    result = await HistoryService(session).handle_custom_date_range(
        user,
        message.text,
        base_filter_key=fsm_data.get("history_base_filter_key"),
    )
    if result.keyboard is not None:
        await state.clear()
    await message.answer(result.message, reply_markup=result.keyboard)


# ---------------------------------------------------------------------------
# Stay management — invoked from /history inline keyboard
# ---------------------------------------------------------------------------


async def _get_user(callback: CallbackQuery, session: AsyncSession) -> User | None:
    if callback.from_user is None:
        return None
    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    return user


@router.callback_query(ManageHistoryCallback.filter())
async def on_manage_history(
    callback: CallbackQuery,
    callback_data: ManageHistoryCallback,
    session: AsyncSession,
) -> None:
    user = await _get_user(callback, session)
    if user is None:
        await callback.answer()
        return

    result = await HistoryService(session).get_manage_selection(
        user,
        filter_key=callback_data.filter_key,
        page=callback_data.page,
    )
    if callback.message is not None:
        await callback.message.edit_text(result.message, reply_markup=result.keyboard)
    await callback.answer()


@router.callback_query(ManageSelectCallback.filter())
async def on_manage_select_stay(
    callback: CallbackQuery,
    callback_data: ManageSelectCallback,
    session: AsyncSession,
) -> None:
    user = await _get_user(callback, session)
    if user is None:
        await callback.answer()
        return

    result = await HistoryService(session).get_stay_action_menu(
        user,
        stay_id=callback_data.stay_id,
        page=callback_data.page,
        filter_key=callback_data.filter_key,
    )
    if callback.message is not None:
        await callback.message.edit_text(result.message, reply_markup=result.keyboard)
    await callback.answer()


@router.callback_query(ManageDeleteCallback.filter())
async def on_manage_delete(
    callback: CallbackQuery,
    callback_data: ManageDeleteCallback,
    session: AsyncSession,
) -> None:
    user = await _get_user(callback, session)
    if user is None:
        await callback.answer()
        return

    result = await HistoryService(session).get_stay_delete_confirmation(
        user,
        stay_id=callback_data.stay_id,
        page=callback_data.page,
        filter_key=callback_data.filter_key,
    )
    if callback.message is not None:
        await callback.message.edit_text(result.message, reply_markup=result.keyboard)
    await callback.answer()


@router.callback_query(ManageConfirmDeleteCallback.filter())
async def on_manage_confirm_delete(
    callback: CallbackQuery,
    callback_data: ManageConfirmDeleteCallback,
    session: AsyncSession,
) -> None:
    user = await _get_user(callback, session)
    if user is None:
        await callback.answer()
        return

    remove_result = await StayService(session).remove_stay(user, callback_data.stay_id)
    if isinstance(remove_result, StayRemoveError):
        if callback.message is not None:
            await callback.message.edit_text(remove_result.message)
        await callback.answer()
        return

    result = await HistoryService(session).handle_history_callback(
        user,
        filter_key=callback_data.filter_key,
        page=callback_data.page,
    )
    if callback.message is not None:
        await callback.message.edit_text(result.message, reply_markup=result.keyboard)
    await callback.answer()


@router.callback_query(ManageEditMenuCallback.filter())
async def on_manage_edit_menu(
    callback: CallbackQuery,
    callback_data: ManageEditMenuCallback,
    session: AsyncSession,
) -> None:
    user = await _get_user(callback, session)
    if user is None:
        await callback.answer()
        return

    result = await HistoryService(session).get_stay_edit_menu(
        user,
        stay_id=callback_data.stay_id,
        page=callback_data.page,
        filter_key=callback_data.filter_key,
    )
    if callback.message is not None:
        await callback.message.edit_text(result.message, reply_markup=result.keyboard)
    await callback.answer()


@router.callback_query(ManageEditFieldCallback.filter())
async def on_manage_edit_field(
    callback: CallbackQuery,
    callback_data: ManageEditFieldCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    user = await _get_user(callback, session)
    if user is None:
        await callback.answer()
        return

    fsm_state_map = {
        "country": HistoryManageStates.editing_country,
        "entry": HistoryManageStates.editing_entry_date,
        "exit": HistoryManageStates.editing_exit_date,
    }
    target_state = fsm_state_map.get(callback_data.field)
    if target_state is None:
        await callback.answer()
        return

    await state.set_state(target_state)
    await state.update_data(
        manage_stay_id=callback_data.stay_id,
        manage_page=callback_data.page,
        manage_filter_key=callback_data.filter_key,
    )

    prompt = HistoryService(session).get_edit_field_prompt(user, callback_data.field)
    if callback.message is not None:
        await callback.message.edit_text(prompt, reply_markup=None)
    await callback.answer()


@router.message(
    HistoryManageStates.editing_country,
    Command("cancel"),
)
@router.message(
    HistoryManageStates.editing_entry_date,
    Command("cancel"),
)
@router.message(
    HistoryManageStates.editing_exit_date,
    Command("cancel"),
)
async def cancel_manage_edit(
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
    await state.clear()
    i18n = LocalizationService(user.language or "en")
    await message.answer(i18n.t("manage.edit_cancelled"))


async def _handle_manage_edit_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    field: str,
) -> None:
    if message.from_user is None or message.text is None:
        return

    text = message.text.strip()
    if text.startswith("/"):
        await state.clear()
        await _dispatch_global_command(message, state, session)
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    fsm_data = await state.get_data()
    stay_id = int(fsm_data["manage_stay_id"])
    page = int(fsm_data["manage_page"])
    filter_key = str(fsm_data["manage_filter_key"])

    svc = StayService(session)
    if field == "country":
        result = await svc.update_stay_country(user, stay_id, text)
    elif field == "entry":
        result = await svc.update_stay_entry_date(user, stay_id, text)
    else:
        result = await svc.update_stay_exit_date(user, stay_id, text)

    if isinstance(result, StayUpdateError):
        await message.answer(result.message)
        return

    await state.clear()

    if isinstance(result, StayCommandConflict):
        await message.answer(result.message, reply_markup=result.keyboard)
        return

    history_result = await HistoryService(session).handle_history_callback(
        user,
        filter_key=filter_key,
        page=page,
    )
    await message.answer(history_result.message, reply_markup=history_result.keyboard)


@router.message(HistoryManageStates.editing_country)
async def on_manage_edit_country_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _handle_manage_edit_input(message, state, session, "country")


@router.message(HistoryManageStates.editing_entry_date)
async def on_manage_edit_entry_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _handle_manage_edit_input(message, state, session, "entry")


@router.message(HistoryManageStates.editing_exit_date)
async def on_manage_edit_exit_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await _handle_manage_edit_input(message, state, session, "exit")
