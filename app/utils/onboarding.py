"""Onboarding enums and display constants (no Telegram imports)."""

from enum import StrEnum
from typing import Final

SUPPORTED_LANGUAGES: Final[tuple[str, ...]] = (
    "en",
    "es",
    "ru",
    "ja",
    "ko",
    "de",
    "fr",
    "zh",
)

LANGUAGE_LABELS: Final[dict[str, str]] = {
    "en": "🇬🇧 English",
    "es": "🇪🇸 Español",
    "ru": "🇷🇺 Русский",
    "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어",
    "de": "🇩🇪 Deutsch",
    "fr": "🇫🇷 Français",
    "zh": "🇨🇳 中文",
}


class DateFormat(StrEnum):
    """Persisted `users.date_format` values."""

    DMY = "dmy"
    MDY = "mdy"
