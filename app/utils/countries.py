"""Country normalization and validation (ISO 3166-1 alpha-2)."""

from typing import Any, TypedDict

import pycountry

# Common aliases → ISO alpha-2 (keys are normalized: lowercase, trimmed, collapsed spaces).
_ALIASES: dict[str, str] = {
    "usa": "US",
    "us": "US",
    "u.s.": "US",
    "u.s.a.": "US",
    "united states": "US",
    "america": "US",
    "uk": "GB",
    "u.k.": "GB",
    "great britain": "GB",
    "britain": "GB",
    "england": "GB",
    "uae": "AE",
    "u.a.e.": "AE",
    "emirates": "AE",
    "south korea": "KR",
    "korea": "KR",
    "republic of korea": "KR",
    "north korea": "KP",
    "dprk": "KP",
    "russia": "RU",
    "russian federation": "RU",
}


class ResolvedCountry(TypedDict):
    code: str
    name: str
    flag: str


def flag_emoji(alpha2: str) -> str:
    """Build a flag emoji from an ISO 3166-1 alpha-2 code (not hardcoded per country)."""
    code = alpha2.upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(ord(char) + 127397) for char in code)


def _normalize_key(user_input: str) -> str:
    return " ".join(user_input.strip().split()).lower()


def _from_code(alpha2: str) -> ResolvedCountry | None:
    country = pycountry.countries.get(alpha_2=alpha2.upper())
    if country is None:
        return None
    return {
        "code": country.alpha_2,
        "name": country.name,
        "flag": flag_emoji(country.alpha_2),
    }


def _country_names(country: Any) -> list[str]:
    names: list[str] = [country.name]
    for attr in ("official_name", "common_name"):
        value = getattr(country, attr, None)
        if value:
            names.append(value)
    return names


def resolve_country(user_input: str) -> ResolvedCountry | None:
    """Resolve free-text country input to ISO code, English name, and flag emoji."""
    if not user_input or not user_input.strip():
        return None

    key = _normalize_key(user_input)

    if key in _ALIASES:
        return _from_code(_ALIASES[key])

    if len(key) == 2 and key.isalpha():
        return _from_code(key)

    try:
        country = pycountry.countries.lookup(user_input.strip())
        return _from_code(country.alpha_2)
    except LookupError:
        pass

    for country in pycountry.countries:
        for name in _country_names(country):
            if _normalize_key(name) == key:
                return _from_code(country.alpha_2)

    return None
