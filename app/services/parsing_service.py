"""Parse Telegram command text into structured arguments."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedCountryCommand:
    country_input: str
    date_str: str


ParsedInCommand = ParsedCountryCommand
ParsedOutCommand = ParsedCountryCommand


class ParsingService:
    """Extract country and date from `/in` messages."""

    @staticmethod
    def parse_in_command(text: str) -> ParsedInCommand | None:
        """Parse `/in Country date` (country may contain spaces)."""
        body = text.strip()
        if body.lower().startswith("/in"):
            body = body[3:].strip()
        elif body.lower().startswith("in"):
            body = body[2:].strip()
        else:
            return None

        parts = body.split()
        if len(parts) < 2:
            return None

        date_str = parts[-1]
        country_input = " ".join(parts[:-1])
        if not country_input:
            return None

        return ParsedCountryCommand(country_input=country_input, date_str=date_str)

    @staticmethod
    def parse_out_command(text: str) -> ParsedOutCommand | None:
        """Parse `/out Country date` (country may contain spaces)."""
        body = text.strip()
        if body.lower().startswith("/out"):
            body = body[4:].strip()
        elif body.lower().startswith("out"):
            body = body[3:].strip()
        else:
            return None

        parts = body.split()
        if len(parts) < 2:
            return None

        date_str = parts[-1]
        country_input = " ".join(parts[:-1])
        if not country_input:
            return None

        return ParsedCountryCommand(country_input=country_input, date_str=date_str)
