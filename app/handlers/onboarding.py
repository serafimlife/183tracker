"""Onboarding inline callback handlers (FSM-gated)."""

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.logger import get_logger
from app.bot.states.onboarding import OnboardingStates
from app.bot.callbacks.onboarding import (
    OnboardingDateFormatCallback,
    OnboardingLanguageCallback,
)
from app.services.onboarding_service import OnboardingService
from app.services.user_service import UserService

router = Router(name="onboarding")
logger = get_logger(__name__)


async def _apply_step(
    callback: CallbackQuery,
    state: FSMContext,
    step,
) -> None:
    """Send step text and sync FSM state."""
    if callback.message is None:
        await callback.answer()
        return

    await callback.message.edit_text(step.text, reply_markup=step.keyboard)

    if step.clear_fsm:
        await state.clear()
    elif step.fsm_state is not None:
        await state.set_state(step.fsm_state)

    await callback.answer()


@router.callback_query(
    OnboardingLanguageCallback.filter(),
    OnboardingStates.language,
)
async def on_language_selected(
    callback: CallbackQuery,
    callback_data: OnboardingLanguageCallback,
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

    onboarding = OnboardingService(session)
    try:
        step = await onboarding.select_language(user, callback_data.code)
    except ValueError:
        logger.warning(
            "onboarding_invalid_language telegram_id=%s code=%s",
            callback.from_user.id,
            callback_data.code,
        )
        await callback.answer("Invalid language.", show_alert=True)
        return

    await _apply_step(callback, state, step)


@router.callback_query(
    OnboardingDateFormatCallback.filter(),
    OnboardingStates.date_format,
)
async def on_date_format_selected(
    callback: CallbackQuery,
    callback_data: OnboardingDateFormatCallback,
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

    onboarding = OnboardingService(session)
    step = await onboarding.select_date_format(user, callback_data.value)
    await _apply_step(callback, state, step)
