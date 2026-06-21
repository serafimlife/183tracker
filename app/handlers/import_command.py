"""Import travel history from CSV or XLSX."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.logger import get_logger
from app.bot.states.import_data import ImportStates
from app.services.import_service import ImportService

logger = get_logger(__name__)

router = Router(name="import")

MAX_IMPORT_BYTES = 5 * 1024 * 1024  # 5 MB

FORMAT_PROMPT = "Choose the date format used in your file:"
UPLOAD_PROMPT = "Now upload your CSV or XLSX file."
MORE_FORMATS_PROMPT = "Choose the date format used in your file:"

DATE_FORMATS: dict[str, tuple[str, str]] = {
    "dmy_long": ("01.03.2026 (DD.MM.YYYY)", "%d.%m.%Y"),
    "dmy_short": ("01.03.26 (DD.MM.YY)", "%d.%m.%y"),
    "iso": ("2026-03-01 (YYYY-MM-DD)", "%Y-%m-%d"),
    "mdy_slash": ("03/01/2026 (MM/DD/YYYY)", "%m/%d/%Y"),
}

MORE_DATE_FORMATS: dict[str, tuple[str, str]] = {
    "dmy_slash": ("01/03/2026 (DD/MM/YYYY)", "%d/%m/%Y"),
    "dmy_dash": ("01-03-2026 (DD-MM-YYYY)", "%d-%m-%Y"),
    "ymd_slash": ("2026/03/01 (YYYY/MM/DD)", "%Y/%m/%d"),
    "d_mon_y": ("01 Mar 2026", "%d %b %Y"),
}

# Kept for the settings import entry point.
INSTRUCTIONS = FORMAT_PROMPT


class ImportDateFormatCallback(CallbackData, prefix="import_date"):
    value: str


def _date_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=ImportDateFormatCallback(value=value).pack(),
                )
            ]
            for value, (label, _) in DATE_FORMATS.items()
        ]
        + [
            [
                InlineKeyboardButton(
                    text="More formats",
                    callback_data=ImportDateFormatCallback(value="more").pack(),
                )
            ]
        ]
    )


def _more_date_format_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=ImportDateFormatCallback(value=value).pack(),
                )
            ]
            for value, (label, _) in MORE_DATE_FORMATS.items()
        ]
        + [
            [
                InlineKeyboardButton(
                    text="Back",
                    callback_data=ImportDateFormatCallback(value="back").pack(),
                )
            ]
        ]
    )


@router.message(Command("import"))
async def cmd_import(message: Message, state: FSMContext) -> None:
    await state.set_state(ImportStates.awaiting_date_format)
    await message.answer(FORMAT_PROMPT, reply_markup=_date_format_keyboard())


@router.callback_query(
    ImportStates.awaiting_date_format,
    ImportDateFormatCallback.filter(),
)
async def on_import_date_format(
    callback: CallbackQuery,
    callback_data: ImportDateFormatCallback,
    state: FSMContext,
) -> None:
    if callback.message is None:
        await callback.answer()
        return

    if callback_data.value == "more":
        await callback.message.answer(
            MORE_FORMATS_PROMPT,
            reply_markup=_more_date_format_keyboard(),
        )
        await callback.answer()
        return

    if callback_data.value == "back":
        await callback.message.answer(
            FORMAT_PROMPT, reply_markup=_date_format_keyboard()
        )
        await callback.answer()
        return

    selected = DATE_FORMATS.get(callback_data.value) or MORE_DATE_FORMATS.get(
        callback_data.value
    )
    if selected is None:
        await callback.answer()
        return

    await state.update_data(import_date_format=selected[1])
    await state.set_state(ImportStates.awaiting_file)
    await callback.message.answer(UPLOAD_PROMPT)
    await callback.answer()


@router.message(ImportStates.awaiting_file, F.document)
async def handle_import_file(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    doc = message.document
    if doc is None or message.from_user is None:
        return

    if doc.file_size and doc.file_size > MAX_IMPORT_BYTES:
        await message.answer(
            f"File too large ({doc.file_size // 1024} KB). Maximum allowed size is 5 MB."
        )
        return

    filename = (doc.file_name or "").lower()
    if filename.endswith(".csv"):
        file_type = "csv"
    elif filename.endswith(".xlsx"):
        file_type = "xlsx"
    else:
        await message.answer("Unsupported file type. Please upload a CSV or XLSX file.")
        return

    data = await state.get_data()
    date_format = data.get("import_date_format")
    if not isinstance(date_format, str):
        await state.set_state(ImportStates.awaiting_date_format)
        await message.answer(FORMAT_PROMPT, reply_markup=_date_format_keyboard())
        return

    try:
        file = await message.bot.get_file(doc.file_id)
        buf = await message.bot.download_file(file.file_path)
        content = buf.read()
    except Exception:
        logger.exception("file_download_failed telegram_id=%s", message.from_user.id)
        await message.answer("Failed to read file. Please upload it again.")
        return

    service = ImportService(session)
    if file_type == "csv":
        try:
            csv_text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            await message.answer("Failed to read CSV file. Please upload it again.")
            return
        result = await service.import_csv(
            message.from_user.id,
            csv_text,
            date_format=date_format,
        )
    else:
        result = await service.import_xlsx(
            message.from_user.id,
            content,
            date_format=date_format,
        )

    await state.clear()
    await message.answer(result.message)
