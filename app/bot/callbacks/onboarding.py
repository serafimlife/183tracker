"""Typed callback data for onboarding inline keyboards."""

from aiogram.filters.callback_data import CallbackData

from app.utils.onboarding import DateFormat


class OnboardingDateFormatCallback(CallbackData, prefix="ob_date"):
    value: DateFormat
