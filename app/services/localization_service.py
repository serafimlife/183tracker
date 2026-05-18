"""Loads UI strings from JSON files in `app/localization/`."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_LOCALIZATION_DIR = Path(__file__).resolve().parent.parent / "localization"


@lru_cache
def _load_locale(language_code: str) -> dict[str, Any]:
    """Load and cache a locale file; fall back to English if missing."""
    path = _LOCALIZATION_DIR / f"{language_code}.json"
    if not path.exists():
        path = _LOCALIZATION_DIR / "en.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class LocalizationService:
    """Resolves dotted keys (e.g. `start.welcome`) for a user's language."""

    def __init__(self, language_code: str = "en") -> None:
        self._language_code = language_code.split("-")[0].lower()
        self._strings = _load_locale(self._language_code)

    def t(self, key: str, **kwargs: Any) -> str:
        """Return translated string; supports `{placeholder}` formatting."""
        parts = key.split(".")
        value: Any = self._strings
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                raise KeyError(f"Missing localization key: {key}")
            value = value[part]
        if not isinstance(value, str):
            raise KeyError(f"Localization key is not a string: {key}")
        return value.format(**kwargs) if kwargs else value
