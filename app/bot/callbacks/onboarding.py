"""Typed callback data for onboarding inline keyboards."""

from aiogram.filters.callback_data import CallbackData

from app.utils.onboarding import DateFormat


class OnboardingLanguageCallback(CallbackData, prefix="ob_lang"):
    code: str


class OnboardingDateFormatCallback(CallbackData, prefix="ob_date"):
    value: DateFormat
