"""Stay entry/exit business logic — validation, residency stats, messages."""

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.stay import (
    CancelTransitionCallback,
    ConfirmTransitionCallback,
    RemoveStayCallback,
)
from app.bot.logger import get_logger
from app.models.stay import Stay
from app.models.user import User
from app.repositories.stay_repository import StayRepository
from app.residency_engine import (
    StayRecord,
    find_overlapping_stay,
    find_untracked_gap,
    stay_duration_days,
)
from app.residency_engine.duplicates import find_duplicate_entry, find_duplicate_exit
from app.residency_engine.gaps import UntrackedGap
from app.residency_engine.transitions import (
    can_transition_on_date,
    find_open_stay_other_country,
)
from app.services.localization_service import LocalizationService
from app.services.parsing_service import ParsingService
from app.services.residency_service import ResidencyService, stays_to_records
from app.utils.countries import ResolvedCountry, flag_emoji, resolve_country
from app.utils.dates import parse_entry_date
from app.utils.onboarding import DateFormat

logger = get_logger(__name__)

ConflictKind = Literal["duplicate", "overlap"]

# FSM payload keys (values stored server-side, not in callback data).
FSM_CLOSE_STAY_ID = "close_stay_id"
FSM_NEW_COUNTRY_CODE = "new_country_code"
FSM_NEW_COUNTRY_NAME = "new_country_name"
FSM_ENTRY_DATE = "entry_date"


@dataclass(frozen=True, slots=True)
class StayCommandSuccess:
    message: str


@dataclass(frozen=True, slots=True)
class StayCommandError:
    message: str


@dataclass(frozen=True, slots=True)
class StayCommandConflict:
    """Actionable conflict — message plus inline remove button."""

    message: str
    keyboard: InlineKeyboardMarkup


@dataclass(frozen=True, slots=True)
class StayCommandTransition:
    """Prompt to close an open stay before entering a new country."""

    message: str
    keyboard: InlineKeyboardMarkup
    fsm_data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class StayRemoveSuccess:
    message: str


@dataclass(frozen=True, slots=True)
class StayRemoveError:
    message: str


StayCommandResult = (
    StayCommandSuccess | StayCommandError | StayCommandConflict | StayCommandTransition
)
StayRemoveResult = StayRemoveSuccess | StayRemoveError


class StayService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = StayRepository(session)

    async def handle_in_command(self, user: User, command_text: str) -> StayCommandResult:
        i18n = LocalizationService(user.language or "en")

        if not user.is_onboarded:
            return StayCommandError(message=i18n.t("in.not_onboarded"))

        parsed = ParsingService.parse_in_command(command_text)
        if parsed is None:
            return StayCommandError(message=i18n.t("in.invalid_usage"))

        country = resolve_country(parsed.country_input)
        if country is None:
            logger.info(
                "country_not_recognized telegram_id=%s input=%r",
                user.telegram_id,
                parsed.country_input,
            )
            return StayCommandError(message=i18n.t("in.country_not_recognized"))

        entry_date = parse_entry_date(
            parsed.date_str,
            date_format=user.date_format,
        )
        if entry_date is None:
            return StayCommandError(message=i18n.t("in.invalid_date"))

        as_of = date.today()
        existing = await self._repo.list_by_user(user.telegram_id)
        records = stays_to_records(existing)

        # 1. Duplicate detection
        duplicate = find_duplicate_entry(records, country["code"], entry_date)
        if duplicate is not None:
            conflict_stay = _stay_from_record(existing, duplicate)
            if conflict_stay is not None:
                return self._conflict_response(
                    i18n, user, conflict_stay, kind="duplicate"
                )

        # 2. Active stay transition (other country) — not an overlap error
        open_other = find_open_stay_other_country(records, country["code"])
        if open_other is not None:
            open_stay = _stay_from_record(existing, open_other)
            if open_stay is not None and can_transition_on_date(open_other, entry_date):
                return self._transition_prompt(
                    i18n, user, open_stay, country, entry_date
                )

        # 3. Overlap validation
        conflict_record = find_overlapping_stay(
            records,
            entry_date,
            None,
            as_of=as_of,
        )
        if conflict_record is not None:
            conflict_stay = _stay_from_record(existing, conflict_record)
            if conflict_stay is not None:
                return self._conflict_response(i18n, user, conflict_stay, kind="overlap")

        # 4. Create stay
        return await self._create_in_stay(
            user, country, entry_date, existing, records, i18n
        )

    async def confirm_country_transition(
        self,
        user: User,
        stay_id: int,
        fsm_data: dict[str, Any],
    ) -> StayCommandResult:
        """Close the open stay and create the new entry (same session transaction)."""
        i18n = LocalizationService(user.language or "en")

        if not _validate_fsm_data(fsm_data):
            return StayCommandError(message=i18n.t("transition.expired"))

        if int(fsm_data[FSM_CLOSE_STAY_ID]) != stay_id:
            logger.warning(
                "transition_stay_id_mismatch telegram_id=%s callback=%s fsm=%s",
                user.telegram_id,
                stay_id,
                fsm_data.get(FSM_CLOSE_STAY_ID),
            )
            return StayCommandError(message=i18n.t("transition.expired"))

        close_stay = await self._repo.get_by_id(stay_id)
        if close_stay is None or close_stay.telegram_id != user.telegram_id:
            return StayCommandError(message=i18n.t("transition.expired"))

        if close_stay.exit_date is not None:
            return StayCommandError(message=i18n.t("transition.already_closed"))

        entry_date = date.fromisoformat(str(fsm_data[FSM_ENTRY_DATE]))
        country: ResolvedCountry = {
            "code": str(fsm_data[FSM_NEW_COUNTRY_CODE]),
            "name": str(fsm_data[FSM_NEW_COUNTRY_NAME]),
            "flag": flag_emoji(str(fsm_data[FSM_NEW_COUNTRY_CODE])),
        }

        if close_stay.country_code == country["code"]:
            return StayCommandError(message=i18n.t("transition.expired"))

        if entry_date < close_stay.entry_date:
            return StayCommandError(message=i18n.t("transition.invalid_dates"))

        existing = await self._repo.list_by_user(user.telegram_id)
        records = stays_to_records(existing)

        conflict_record = find_overlapping_stay(
            records,
            entry_date,
            None,
            exclude_stay_id=close_stay.id,
            as_of=date.today(),
        )
        if conflict_record is not None:
            conflict_stay = _stay_from_record(existing, conflict_record)
            if conflict_stay is not None:
                return self._conflict_response(i18n, user, conflict_stay, kind="overlap")

        await self._repo.close_stay(close_stay, entry_date)
        logger.info(
            "transition_closed telegram_id=%s stay_id=%s exit_date=%s",
            user.telegram_id,
            close_stay.id,
            entry_date.isoformat(),
        )

        new_stay = await self._repo.create_entry(
            user.telegram_id,
            country_code=country["code"],
            country_name=country["name"],
            entry_date=entry_date,
        )
        logger.info(
            "transition_opened telegram_id=%s country_code=%s entry_date=%s",
            user.telegram_id,
            country["code"],
            entry_date.isoformat(),
        )

        all_stays = existing + [new_stay]
        close_stay.exit_date = entry_date
        gap = find_untracked_gap(records, entry_date)
        message = self._build_transition_success_message(
            i18n,
            user,
            close_stay,
            country,
            entry_date,
            all_stays,
            new_stay,
            gap,
        )
        return StayCommandSuccess(message=message)

    def cancel_country_transition(self, user: User) -> StayCommandSuccess:
        i18n = LocalizationService(user.language or "en")
        return StayCommandSuccess(message=i18n.t("transition.cancelled"))

    async def handle_out_command(self, user: User, command_text: str) -> StayCommandResult:
        i18n = LocalizationService(user.language or "en")

        if not user.is_onboarded:
            return StayCommandError(message=i18n.t("out.not_onboarded"))

        parsed = ParsingService.parse_out_command(command_text)
        if parsed is None:
            return StayCommandError(message=i18n.t("out.invalid_usage"))

        country = resolve_country(parsed.country_input)
        if country is None:
            return StayCommandError(message=i18n.t("in.country_not_recognized"))

        exit_date = parse_entry_date(
            parsed.date_str,
            date_format=user.date_format,
        )
        if exit_date is None:
            return StayCommandError(message=i18n.t("out.invalid_date"))

        existing = await self._repo.list_by_user(user.telegram_id)
        records = stays_to_records(existing)

        open_stay = await self._repo.get_open_stay(user.telegram_id, country["code"])
        if open_stay is None:
            duplicate = find_duplicate_exit(records, country["code"], exit_date)
            if duplicate is not None:
                conflict_stay = _stay_from_record(existing, duplicate)
                if conflict_stay is not None:
                    return self._conflict_response(
                        i18n, user, conflict_stay, kind="duplicate"
                    )
            latest_closed = _latest_closed_stay(existing, country["code"])
            if latest_closed is not None and latest_closed.exit_date != exit_date:
                return self._closed_stay_correction_response(
                    i18n, user, latest_closed
                )
            return StayCommandError(
                message=i18n.t("out.no_open_stay", country=country["name"])
            )

        if exit_date < open_stay.entry_date:
            return StayCommandError(message=i18n.t("out.exit_before_entry"))

        as_of = date.today()
        conflict_record = find_overlapping_stay(
            records,
            open_stay.entry_date,
            exit_date,
            exclude_stay_id=open_stay.id,
            as_of=as_of,
        )
        if conflict_record is not None:
            conflict_stay = _stay_from_record(existing, conflict_record)
            if conflict_stay is not None:
                return self._conflict_response(i18n, user, conflict_stay, kind="overlap")

        await self._repo.close_stay(open_stay, exit_date)
        logger.info(
            "stay_exit_recorded telegram_id=%s country_code=%s exit_date=%s",
            user.telegram_id,
            country["code"],
            exit_date.isoformat(),
        )

        duration = stay_duration_days(
            open_stay.entry_date, exit_date, as_of=exit_date
        )
        message = self._build_out_message(
            i18n,
            user,
            country,
            exit_date,
            existing,
            open_stay,
            duration,
        )
        return StayCommandSuccess(message=message)

    async def remove_stay(self, user: User, stay_id: int) -> StayRemoveResult:
        """Delete a stay after verifying it belongs to the requesting user."""
        i18n = LocalizationService(user.language or "en")

        stay = await self._repo.get_by_id(stay_id)
        if stay is None:
            logger.warning(
                "stay_remove_not_found telegram_id=%s stay_id=%s",
                user.telegram_id,
                stay_id,
            )
            return StayRemoveError(message=i18n.t("stay.remove_not_found"))

        if stay.telegram_id != user.telegram_id:
            logger.warning(
                "stay_remove_forbidden telegram_id=%s stay_id=%s owner=%s",
                user.telegram_id,
                stay_id,
                stay.telegram_id,
            )
            return StayRemoveError(message=i18n.t("stay.remove_forbidden"))

        await self._repo.delete(stay)
        logger.info(
            "stay_removed telegram_id=%s stay_id=%s country_code=%s",
            user.telegram_id,
            stay_id,
            stay.country_code,
        )
        return StayRemoveSuccess(message=i18n.t("stay.removed"))

    async def _create_in_stay(
        self,
        user: User,
        country: ResolvedCountry,
        entry_date: date,
        existing: list[Stay],
        records: list[StayRecord],
        i18n: LocalizationService,
    ) -> StayCommandSuccess:
        stay = await self._repo.create_entry(
            user.telegram_id,
            country_code=country["code"],
            country_name=country["name"],
            entry_date=entry_date,
        )
        logger.info(
            "stay_entry_created telegram_id=%s country_code=%s entry_date=%s",
            user.telegram_id,
            country["code"],
            entry_date.isoformat(),
        )

        all_stays = existing + [stay]
        gap = find_untracked_gap(records, entry_date)
        message = self._build_in_message(
            i18n,
            user,
            country,
            entry_date,
            all_stays,
            stay,
            gap,
        )
        return StayCommandSuccess(message=message)

    def _transition_prompt(
        self,
        i18n: LocalizationService,
        user: User,
        open_stay: Stay,
        new_country: ResolvedCountry,
        entry_date: date,
    ) -> StayCommandTransition:
        present = i18n.t("stay.present")
        active_period = ResidencyService.format_stay_period(
            open_stay,
            date_format=user.date_format,
            present_label=present,
        )
        prior_flag = flag_emoji(open_stay.country_code)
        new_flag = new_country["flag"]
        entry_display = _format_short_date(entry_date, user.date_format)

        message = i18n.t(
            "transition.prompt",
            active_stay=active_period,
            prior_flag=prior_flag,
            prior_country=open_stay.country_name,
            new_flag=new_flag,
            new_country=new_country["name"],
            entry_date=entry_display,
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.t(
                            "transition.confirm_button",
                            country=open_stay.country_name,
                        ),
                        callback_data=ConfirmTransitionCallback(
                            stay_id=open_stay.id
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=i18n.t("transition.cancel_button"),
                        callback_data=CancelTransitionCallback().pack(),
                    )
                ],
            ]
        )
        fsm_data = {
            FSM_CLOSE_STAY_ID: open_stay.id,
            FSM_NEW_COUNTRY_CODE: new_country["code"],
            FSM_NEW_COUNTRY_NAME: new_country["name"],
            FSM_ENTRY_DATE: entry_date.isoformat(),
        }
        logger.info(
            "transition_prompted telegram_id=%s close_stay_id=%s new_country=%s entry_date=%s",
            user.telegram_id,
            open_stay.id,
            new_country["code"],
            entry_date.isoformat(),
        )
        return StayCommandTransition(
            message=message, keyboard=keyboard, fsm_data=fsm_data
        )

    def _build_transition_success_message(
        self,
        i18n: LocalizationService,
        user: User,
        closed_stay: Stay,
        new_country: ResolvedCountry,
        entry_date: date,
        stays: list[Stay],
        new_stay: Stay,
        gap: UntrackedGap | None,
    ) -> str:
        closed_line = i18n.t(
            "transition.closed",
            flag=flag_emoji(closed_stay.country_code),
            country=closed_stay.country_name,
            date=_format_short_date(entry_date, user.date_format),
        )
        in_message = self._build_in_message(
            i18n, user, new_country, entry_date, stays, new_stay, gap
        )
        return f"{closed_line}\n\n{in_message}"

    def _conflict_response(
        self,
        i18n: LocalizationService,
        user: User,
        stay: Stay,
        *,
        kind: ConflictKind,
    ) -> StayCommandConflict:
        present = i18n.t("stay.present")
        period = ResidencyService.format_stay_period(
            stay,
            date_format=user.date_format,
            present_label=present,
        )
        key = "stay.duplicate_exists" if kind == "duplicate" else "stay.overlap_exists"
        message = i18n.t(key, stay_period=period)
        keyboard = self._remove_keyboard(i18n, user, stay, present_label=present)
        return StayCommandConflict(message=message, keyboard=keyboard)

    def _closed_stay_correction_response(
        self,
        i18n: LocalizationService,
        user: User,
        stay: Stay,
    ) -> StayCommandConflict:
        present = i18n.t("stay.present")
        period = ResidencyService.format_stay_period(
            stay,
            date_format=user.date_format,
            present_label=present,
        )
        message = i18n.t(
            "out.already_closed_correction",
            flag=flag_emoji(stay.country_code),
            country=stay.country_name,
            stay_period=period,
        )
        keyboard = self._remove_keyboard(i18n, user, stay, present_label=present)
        return StayCommandConflict(message=message, keyboard=keyboard)

    def _remove_keyboard(
        self,
        i18n: LocalizationService,
        user: User,
        stay: Stay,
        *,
        present_label: str,
    ) -> InlineKeyboardMarkup:
        date_range = ResidencyService.format_stay_range_compact(
            stay,
            date_format=user.date_format,
            present_label=present_label,
        )
        label = i18n.t(
            "stay.remove_button",
            country=stay.country_name,
            range=date_range,
        )
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=RemoveStayCallback(stay_id=stay.id).pack(),
                    )
                ]
            ]
        )

    def _build_in_message(
        self,
        i18n: LocalizationService,
        user: User,
        country: ResolvedCountry,
        entry_date: date,
        stays: list[Stay],
        active_stay: Stay,
        gap: UntrackedGap | None,
    ) -> str:
        as_of = date.today()
        stats = ResidencyService.stats_for_country(
            stays,
            country["code"],
            as_of=as_of,
            active_stay=active_stay,
        )
        parts = [
            i18n.t(
                "in.success",
                flag=country["flag"],
                country=country["name"],
                date=_format_short_date(entry_date, user.date_format),
            ),
            "",
            i18n.t(
                "in.current_stay",
                days=stats.current_stay_days or 1,
            ),
            "",
            i18n.t("in.year_totals_header", year=stats.year),
            i18n.t("in.calendar_year_line", days=stats.calendar_year_days),
            i18n.t("in.rolling_line", days=stats.rolling_365_days),
            "",
            i18n.t("in.remaining_line", days=stats.remaining_days),
        ]
        if gap is not None:
            parts.extend(["", self._gap_message(i18n, gap, user.date_format, country)])
        return "\n".join(parts)

    def _build_out_message(
        self,
        i18n: LocalizationService,
        user: User,
        country: ResolvedCountry,
        exit_date: date,
        stays: list[Stay],
        closed_stay: Stay,
        duration: int,
    ) -> str:
        as_of = date.today()
        closed_stay.exit_date = exit_date
        stats = ResidencyService.stats_for_country(
            stays,
            country["code"],
            as_of=as_of,
        )
        return "\n".join(
            [
                i18n.t(
                    "out.success",
                    flag=country["flag"],
                    country=country["name"],
                    date=_format_short_date(exit_date, user.date_format),
                ),
                "",
                i18n.t("out.duration", days=duration),
                "",
                i18n.t("out.year_totals_header", year=stats.year),
                i18n.t("out.calendar_year_line", days=stats.calendar_year_days),
                i18n.t("out.rolling_line", days=stats.rolling_365_days),
                "",
                i18n.t("out.remaining_line", days=stats.remaining_days),
            ]
        )

    def _gap_message(
        self,
        i18n: LocalizationService,
        gap: UntrackedGap,
        date_format: str | None,
        new_country: ResolvedCountry,
    ) -> str:
        prior_flag = flag_emoji(gap.prior.country_code)
        new_flag = new_country["flag"]
        return i18n.t(
            "stay.gap_warning",
            from_country=f"{prior_flag} {gap.prior.country_name}",
            to_country=f"{new_flag} {new_country['name']}",
            gap_start=_format_short_date(gap.gap_start, date_format),
            gap_end=_format_short_date(gap.gap_end, date_format),
            gap_days=gap.gap_days,
        )


def _validate_fsm_data(data: dict[str, Any]) -> bool:
    required = (
        FSM_CLOSE_STAY_ID,
        FSM_NEW_COUNTRY_CODE,
        FSM_NEW_COUNTRY_NAME,
        FSM_ENTRY_DATE,
    )
    return all(key in data for key in required)


def _stay_from_record(stays: list[Stay], record: StayRecord) -> Stay | None:
    if record.stay_id is not None:
        for stay in stays:
            if stay.id == record.stay_id:
                return stay
    for stay in stays:
        if (
            stay.country_code == record.country_code
            and stay.entry_date == record.entry_date
            and stay.exit_date == record.exit_date
        ):
            return stay
    return None


def _latest_closed_stay(stays: list[Stay], country_code: str) -> Stay | None:
    closed = [
        stay
        for stay in stays
        if stay.country_code == country_code and stay.exit_date is not None
    ]
    if not closed:
        return None
    return max(
        closed,
        key=lambda stay: (
            stay.exit_date or date.min,
            stay.entry_date,
            stay.id or 0,
        ),
    )


def _format_short_date(value: date, date_format: str | None) -> str:
    if date_format == DateFormat.MDY.value:
        return f"{value.strftime('%B')} {value.day}, {value.year}"
    return f"{value.day} {value.strftime('%B')} {value.year}"
