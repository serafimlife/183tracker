"""`/settings` command — date format, import, export, and delete-all-data."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states.import_data import ImportStates
from app.handlers.import_command import (
    FORMAT_PROMPT,
    _date_format_keyboard as _import_date_format_keyboard,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.export_service import ExportService
from app.services.localization_service import LocalizationService
from app.services.user_service import UserService
from app.utils.onboarding import DEFAULT_LANGUAGE, DateFormat

router = Router(name="settings")

DELETE_ALL_TRIGGER = "DELETE ALL DATA"

_FORMAT_LABELS: dict[str, str] = {
    DateFormat.DMY.value: "DD.MM.YY",
    DateFormat.MDY.value: "MM.DD.YY",
}


class SettingsMenuCallback(CallbackData, prefix="settings_menu"):
    action: str


class SettingsDateFormatCallback(CallbackData, prefix="settings_date"):
    value: str


def _settings_keyboard(
    i18n: LocalizationService, date_format: str | None = None
) -> InlineKeyboardMarkup:
    date_label = _FORMAT_LABELS.get(date_format or DateFormat.DMY.value, "DD.MM.YY")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.t("settings.date_format", format=date_label),
                    callback_data=SettingsMenuCallback(action="date_format").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("settings.import_data"),
                    callback_data=SettingsMenuCallback(action="import").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("settings.export_data"),
                    callback_data=SettingsMenuCallback(action="export").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.t("settings.delete_data"),
                    callback_data=SettingsMenuCallback(action="delete").pack(),
                )
            ],
        ]
    )


def _date_format_keyboard(i18n: LocalizationService) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=i18n.t("onboarding.date_format.dmy"),
                callback_data=SettingsDateFormatCallback(
                    value=DateFormat.DMY.value
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text=i18n.t("onboarding.date_format.mdy"),
                callback_data=SettingsDateFormatCallback(
                    value=DateFormat.MDY.value
                ).pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="← Back",
                callback_data=SettingsMenuCallback(action="back").pack(),
            )
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def cmd_settings(
    message: Message,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )
    i18n = LocalizationService(user.language or DEFAULT_LANGUAGE)
    await message.answer(
        i18n.t("settings.menu"),
        reply_markup=_settings_keyboard(i18n, user.date_format),
    )


@router.callback_query(SettingsMenuCallback.filter())
async def on_settings_menu(
    callback: CallbackQuery,
    callback_data: SettingsMenuCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )
    i18n = LocalizationService(user.language or DEFAULT_LANGUAGE)

    match callback_data.action:
        case "date_format":
            await callback.message.edit_text(
                i18n.t("settings.date_format_title"),
                reply_markup=_date_format_keyboard(i18n),
            )
        case "import":
            await state.set_state(ImportStates.awaiting_date_format)
            await callback.message.answer(
                FORMAT_PROMPT,
                reply_markup=_import_date_format_keyboard(),
            )
        case "export":
            csv_content = await ExportService(session).generate_csv(user.telegram_id)
            csv_bytes = csv_content.encode("utf-8")
            await callback.message.answer(i18n.t("settings.export_message"))
            await callback.message.answer_document(
                BufferedInputFile(csv_bytes, filename="travel_history.csv"),
            )
        case "delete":
            await callback.message.answer(i18n.t("settings.delete_warning"))
        case "back":
            await callback.message.edit_text(
                i18n.t("settings.menu"),
                reply_markup=_settings_keyboard(i18n, user.date_format),
            )

    await callback.answer()


@router.callback_query(SettingsDateFormatCallback.filter())
async def on_settings_date_format(
    callback: CallbackQuery,
    callback_data: SettingsDateFormatCallback,
    session: AsyncSession,
) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer()
        return
    if callback_data.value not in (DateFormat.DMY.value, DateFormat.MDY.value):
        await callback.answer()
        return

    user_service = UserService(session)
    user, _ = await user_service.get_or_create(
        callback.from_user.id,
        username=callback.from_user.username,
        first_name=callback.from_user.first_name,
    )

    repo = UserRepository(session)
    await repo.set_date_format(user, callback_data.value)

    i18n = LocalizationService(user.language or DEFAULT_LANGUAGE)
    await callback.message.edit_text(
        i18n.t("settings.menu"),
        reply_markup=_settings_keyboard(i18n, callback_data.value),
    )
    await callback.answer()


@router.message(F.text == DELETE_ALL_TRIGGER)
async def on_delete_all_data(
    message: Message,
    session: AsyncSession,
) -> None:
    if message.from_user is None:
        return

    user = await session.get(User, message.from_user.id)
    if user is not None:
        await session.delete(user)
        await session.flush()

    await message.answer("Your data has been permanently deleted.")
