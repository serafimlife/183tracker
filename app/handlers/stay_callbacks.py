"""Inline callbacks for stay management."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.stay import (
    CancelTransitionCallback,
    ConfirmTransitionCallback,
    RemoveStayCallback,
)
from app.bot.states.stay_transition import StayTransitionStates
from app.services.stay_service import (
    StayCommandConflict,
    StayCommandTransition,
    StayRemoveError,
    StayService,
)
from app.services.user_service import UserService

router = Router(name="stay_callbacks")


@router.callback_query(RemoveStayCallback.filter())
async def on_remove_stay(
    callback: CallbackQuery,
    callback_data: RemoveStayCallback,
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

    result = await StayService(session).remove_stay(user, callback_data.stay_id)

    if callback.message is not None:
        if isinstance(result, StayRemoveError):
            await callback.message.answer(result.message)
        else:
            await callback.message.edit_text(result.message)

    await callback.answer()


@router.callback_query(
    ConfirmTransitionCallback.filter(),
    StayTransitionStates.confirming,
)
async def on_confirm_transition(
    callback: CallbackQuery,
    callback_data: ConfirmTransitionCallback,
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

    fsm_data = await state.get_data()
    result = await StayService(session).confirm_country_transition(
        user, callback_data.stay_id, fsm_data
    )
    await state.clear()

    if callback.message is None:
        await callback.answer()
        return

    if isinstance(result, StayCommandConflict):
        await callback.message.edit_text(result.message, reply_markup=result.keyboard)
    else:
        await callback.message.edit_text(result.message)

    await callback.answer()


@router.callback_query(
    CancelTransitionCallback.filter(),
    StayTransitionStates.confirming,
)
async def on_cancel_transition(
    callback: CallbackQuery,
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

    result = StayService(session).cancel_country_transition(user)
    await state.clear()

    if callback.message is not None:
        await callback.message.edit_text(result.message)

    await callback.answer()
