"""`/help` command — command reference."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router(name="help")

HELP_TEXT = """🏝 Residency Tracker
Track your stays and residency days.

✈️ TRAVEL
/in Thailand today — entering a country
/out Thailand today — leaving a country
/log Thailand 01.01.2026 15.01.2026 — add a past stay

📍 STATUS
/where — current stay + days left

📖 HISTORY
/history — all stays
/history 2026 — by year
/history Thailand — by country
/history Thailand 01.01.2026 01.05.2026 — by country + dates

📊 REPORTS
/report — full summary
/report 2026 — by year
/report Thailand — by country
/report Thailand 01.01.2026 01.05.2026 — by country + dates

⚙️ SETTINGS
/settings — date format, import/export, delete data"""


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
