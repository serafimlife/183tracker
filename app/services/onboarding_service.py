"""Onboarding flow — messages, keyboards, and persistence rules."""

from dataclasses import dataclass

from aiogram.fsm.state import State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.logger import get_logger
from app.bot.states.onboarding import OnboardingStates
from app.bot.callbacks.onboarding import OnboardingDateFormatCallback
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.localization_service import LocalizationService
from app.utils.onboarding import DEFAULT_LANGUAGE, DateFormat

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OnboardingStep:
    """Payload for handlers to send/edit a Telegram message."""

    text: str
    keyboard: InlineKeyboardMarkup | None = None
    fsm_state: State | None = None
    clear_fsm: bool = False


class OnboardingService:
    """Business logic for /start onboarding and returning users."""

    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    @staticmethod
    def is_onboarded(user: User) -> bool:
        return user.is_onboarded

    def welcome_back(self, user: User) -> OnboardingStep:
        i18n = LocalizationService(user.language or DEFAULT_LANGUAGE)
        name = user.first_name or "there"
        return OnboardingStep(
            text=i18n.t("start.welcome_back", name=name),
            clear_fsm=True,
        )

    def resume_onboarding(self, user: User) -> OnboardingStep:
        """Show date format picker if user hasn't finished onboarding."""
        i18n = LocalizationService(user.language or DEFAULT_LANGUAGE)
        return OnboardingStep(
            text=i18n.t("onboarding.choose_date_format"),
            keyboard=self._date_format_keyboard(i18n),
            fsm_state=OnboardingStates.date_format,
        )

    async def start_onboarding(self, user: User) -> OnboardingStep:
        """Welcome new user, set default language, and prompt date format."""
        await self._repo.set_language(user, DEFAULT_LANGUAGE)
        logger.info("onboarding_started telegram_id=%s", user.telegram_id)
        i18n = LocalizationService(DEFAULT_LANGUAGE)
        return OnboardingStep(
            text=i18n.t("onboarding.welcome"),
            keyboard=self._date_format_keyboard(i18n),
            fsm_state=OnboardingStates.date_format,
        )

    async def select_date_format(
        self, user: User, date_format: DateFormat
    ) -> OnboardingStep:
        await self._repo.set_date_format(user, date_format.value)
        logger.info(
            "onboarding_completed telegram_id=%s date_format=%s",
            user.telegram_id,
            date_format.value,
        )

        i18n = LocalizationService(user.language or DEFAULT_LANGUAGE)
        return OnboardingStep(
            text=i18n.t("onboarding.complete"),
            clear_fsm=True,
        )

    @staticmethod
    def _date_format_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.t("onboarding.date_format.dmy"),
                        callback_data=OnboardingDateFormatCallback(
                            value=DateFormat.DMY
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=i18n.t("onboarding.date_format.mdy"),
                        callback_data=OnboardingDateFormatCallback(
                            value=DateFormat.MDY
                        ).pack(),
                    )
                ],
            ]
        )
