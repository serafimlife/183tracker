"""Onboarding flow — messages, keyboards, and persistence rules."""

from dataclasses import dataclass

from aiogram.fsm.state import State
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.logger import get_logger
from app.bot.states.onboarding import OnboardingStates
from app.bot.callbacks.onboarding import (
    OnboardingDateFormatCallback,
    OnboardingLanguageCallback,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.localization_service import LocalizationService
from app.utils.onboarding import (
    SUPPORTED_LANGUAGES,
    LANGUAGE_LABELS,
    DateFormat,
)

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
        i18n = LocalizationService(user.language or "en")
        name = user.first_name or "there"
        return OnboardingStep(
            text=i18n.t("start.welcome_back", name=name),
            clear_fsm=True,
        )

    def resume_onboarding(self, user: User) -> OnboardingStep:
        """Continue onboarding if language was saved but date format was not."""
        if user.language is None:
            return self.start_onboarding(user)

        i18n = LocalizationService(user.language)
        return OnboardingStep(
            text=i18n.t("onboarding.choose_date_format"),
            keyboard=self._date_format_keyboard(i18n),
            fsm_state=OnboardingStates.date_format,
        )

    def start_onboarding(self, user: User) -> OnboardingStep:
        """Step 1 — fixed English welcome before language is chosen."""
        logger.info("onboarding_started telegram_id=%s", user.telegram_id)
        i18n = LocalizationService("en")
        return OnboardingStep(
            text=i18n.t("onboarding.welcome"),
            keyboard=self._language_keyboard(),
            fsm_state=OnboardingStates.language,
        )

    async def select_language(self, user: User, language: str) -> OnboardingStep:
        if language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {language}")

        await self._repo.set_language(user, language)
        logger.info(
            "onboarding_language_selected telegram_id=%s language=%s",
            user.telegram_id,
            language,
        )

        i18n = LocalizationService(language)
        return OnboardingStep(
            text=i18n.t("onboarding.choose_date_format"),
            keyboard=self._date_format_keyboard(i18n),
            fsm_state=OnboardingStates.date_format,
        )

    async def select_date_format(
        self, user: User, date_format: DateFormat
    ) -> OnboardingStep:
        await self._repo.set_date_format(user, date_format.value)
        logger.info(
            "onboarding_completed telegram_id=%s language=%s date_format=%s",
            user.telegram_id,
            user.language,
            date_format.value,
        )

        i18n = LocalizationService(user.language or "en")
        return OnboardingStep(
            text=i18n.t("onboarding.complete"),
            clear_fsm=True,
        )

    @staticmethod
    def _language_keyboard() -> InlineKeyboardMarkup:
        rows = [
            [
                InlineKeyboardButton(
                    text=LANGUAGE_LABELS[code],
                    callback_data=OnboardingLanguageCallback(code=code).pack(),
                )
            ]
            for code in SUPPORTED_LANGUAGES
        ]
        return InlineKeyboardMarkup(inline_keyboard=rows)

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
