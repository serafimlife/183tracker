"""`/start` command — registration and onboarding entry."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.onboarding_service import OnboardingService
from app.services.user_service import UserService

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Register user, then onboard or welcome back."""
    if message.from_user is None:
        return

    tg_user = message.from_user
    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )

    onboarding = OnboardingService(session)

    if onboarding.is_onboarded(user):
        step = onboarding.welcome_back(user)
        await state.clear()
    elif user.language is not None:
        step = onboarding.resume_onboarding(user)
    else:
        step = onboarding.start_onboarding(user)

    if step.fsm_state is not None:
        await state.set_state(step.fsm_state)

    await message.answer(step.text, reply_markup=step.keyboard)
