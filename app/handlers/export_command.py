"""`/export` command — sends travel history as CSV."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.export_service import ExportService
from app.services.user_service import UserService

router = Router(name="export")


@router.message(Command("export"))
async def cmd_export(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    csv_content = await ExportService(session).generate_csv(user.telegram_id)
    csv_bytes = csv_content.encode("utf-8")

    await message.answer("Here's your complete travel history in CSV format.")
    await message.answer_document(
        BufferedInputFile(csv_bytes, filename="travel_history.csv"),
    )
