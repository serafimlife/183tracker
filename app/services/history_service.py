"""Business logic for /where and /history."""

from dataclasses import dataclass
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callbacks.history import (
    HistoryPageCallback,
    ManageConfirmDeleteCallback,
    ManageDeleteCallback,
    ManageEditFieldCallback,
    ManageEditMenuCallback,
    ManageHistoryCallback,
    ManageSelectCallback,
)
from app.models.stay import Stay
from app.models.user import User
from app.repositories.stay_repository import StayRepository
from app.residency_engine import stay_duration_days
from app.residency_engine.intervals import days_in_range_within
from app.residency_engine.thresholds import calculate_remaining_days
from app.services.localization_service import LocalizationService
from app.services.parsing_service import ParsedHistoryCommand, ParsingService
from app.services.residency_service import ResidencyService
from app.utils.countries import flag_emoji, resolve_country
from app.utils.formatters import format_duration_days, get_threshold_indicator
from app.utils.onboarding import DateFormat

HISTORY_PAGE_SIZE = 10
HISTORY_MESSAGE_LIMIT = 3500


@dataclass(frozen=True, slots=True)
class MessageResult:
    message: str
    keyboard: InlineKeyboardMarkup | None = None
    fsm_data: dict[str, str] | None = None


class HistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = StayRepository(session)

    async def handle_where_command(self, user: User) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        stays = await self._repo.list_by_user(user.telegram_id)
        active = _latest_open_stay(stays)
        if active is None:
            return MessageResult(message=i18n.t("where.no_active"))

        as_of = date.today()
        stats = ResidencyService.stats_for_country(
            stays,
            active.country_code,
            as_of=as_of,
            active_stay=active,
        )
        current_days = stay_duration_days(active.entry_date, None, as_of=as_of)
        calendar_remaining = calculate_remaining_days(stats.calendar_year_days)
        rolling_remaining = calculate_remaining_days(stats.rolling_365_days)
        message = i18n.t(
            "where.active",
            flag=flag_emoji(active.country_code),
            country=active.country_name,
            entry_date=_format_display_date(active.entry_date, user.date_format),
            current_duration=format_duration_days(current_days, i18n),
            year=stats.year,
            calendar_days=format_duration_days(stats.calendar_year_days, i18n),
            rolling_days=format_duration_days(stats.rolling_365_days, i18n),
            calendar_remaining=format_duration_days(calendar_remaining, i18n),
            rolling_remaining=format_duration_days(rolling_remaining, i18n),
            calendar_indicator=get_threshold_indicator(calendar_remaining),
            rolling_indicator=get_threshold_indicator(rolling_remaining),
        )
        return MessageResult(message=message)

    async def handle_history_command(
        self,
        user: User,
        command_text: str,
        *,
        page: int = 0,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        parsed = ParsingService.parse_history_command(
            command_text,
            date_format=user.date_format,
        )
        if parsed is None:
            return MessageResult(message=i18n.t("history.invalid_usage"))
        return await self.history_for_query(user, parsed, page=page)

    async def handle_history_callback(
        self,
        user: User,
        filter_key: str,
        *,
        page: int,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        base_filter_key = _custom_base_filter_key(filter_key)
        if base_filter_key is not None:
            return MessageResult(
                message=i18n.t("history.custom_dates_prompt"),
                fsm_data={"history_base_filter_key": base_filter_key},
            )
        parsed = _query_from_filter_key(filter_key)
        if parsed is None:
            return MessageResult(message=i18n.t("history.invalid_usage"))
        return await self.history_for_query(user, parsed, page=page)

    async def handle_custom_date_range(
        self,
        user: User,
        text: str,
        *,
        base_filter_key: str | None = None,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        parsed = ParsingService.parse_history_date_range(
            text,
            date_format=user.date_format,
        )
        if parsed is None:
            return MessageResult(message=i18n.t("history.custom_dates_error"))
        if base_filter_key is not None:
            base_query = _query_from_filter_key(base_filter_key)
            if base_query is None:
                return MessageResult(message=i18n.t("history.invalid_usage"))
            parsed = _merge_custom_date_range(base_query, parsed)
            if parsed is None:
                return MessageResult(
                    message=i18n.t("history.empty"),
                    keyboard=self._history_keyboard(
                        i18n,
                        ParsingService.parse_history_date_range(
                            text,
                            date_format=user.date_format,
                        )
                        or ParsedHistoryCommand(),
                        page=0,
                        total=0,
                    ),
                )
        return await self.history_for_query(user, parsed, page=0)

    def cancel_custom_dates(self, user: User) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        return MessageResult(message=i18n.t("history.custom_dates_cancelled"))

    async def get_manage_selection(
        self,
        user: User,
        filter_key: str,
        page: int,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        parsed = _query_from_filter_key(filter_key)
        if parsed is None:
            return MessageResult(message=i18n.t("history.invalid_usage"))

        country_code: str | None = None
        if parsed.country_input is not None:
            country = resolve_country(parsed.country_input)
            if country is not None:
                country_code = country["code"]

        window = _date_window(parsed)
        stays = await self._repo.list_by_user(user.telegram_id)
        filtered = [
            s
            for s in stays
            if _matches_history_filter(s, country_code=country_code, window=window)
        ]
        filtered.sort(key=lambda s: (s.entry_date, s.id or 0), reverse=True)

        if not filtered:
            return MessageResult(message=i18n.t("history.empty"))

        total = len(filtered)
        safe_page = max(0, min(page, (total - 1) // HISTORY_PAGE_SIZE))
        start = safe_page * HISTORY_PAGE_SIZE
        end = min(start + HISTORY_PAGE_SIZE, total)
        page_stays = filtered[start:end]

        parts = [i18n.t("manage.select_prompt"), ""]
        for idx, stay in enumerate(page_stays, 1):
            parts.append(
                f"{idx}. {self._format_history_stay(i18n, user, stay, window)}"
            )

        number_buttons = [
            InlineKeyboardButton(
                text=str(idx),
                callback_data=ManageSelectCallback(
                    stay_id=stay.id,
                    page=safe_page,
                    filter_key=filter_key,
                ).pack(),
            )
            for idx, stay in enumerate(page_stays, 1)
        ]
        _max_per_row = 8
        button_rows: list[list[InlineKeyboardButton]] = [
            number_buttons[i : i + _max_per_row]
            for i in range(0, len(number_buttons), _max_per_row)
        ]
        current_year = date.today().year
        year_buttons = [
            InlineKeyboardButton(
                text=str(y),
                callback_data=ManageHistoryCallback(page=0, filter_key=f"y{y}").pack(),
            )
            for y in (current_year, current_year - 1, current_year - 2)
        ]
        back_button = InlineKeyboardButton(
            text=i18n.t("manage.back_button"),
            callback_data=HistoryPageCallback(
                page=safe_page, filter_key=filter_key
            ).pack(),
        )
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[*button_rows, year_buttons, [back_button]]
        )
        return MessageResult(message="\n".join(parts), keyboard=keyboard)

    async def get_stay_action_menu(
        self,
        user: User,
        stay_id: int,
        page: int,
        filter_key: str,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        stay = await self._repo.get_by_id(stay_id)
        if stay is None or stay.telegram_id != user.telegram_id:
            return MessageResult(message=i18n.t("manage.stay_not_found"))

        parsed = _query_from_filter_key(filter_key)
        window = _date_window(parsed) if parsed is not None else None
        stay_text = self._format_history_stay(i18n, user, stay, window)
        message = f"{stay_text}\n\n{i18n.t('manage.action_prompt')}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.t("manage.edit_button"),
                        callback_data=ManageEditMenuCallback(
                            stay_id=stay_id, page=page, filter_key=filter_key
                        ).pack(),
                    ),
                    InlineKeyboardButton(
                        text=i18n.t("manage.delete_button"),
                        callback_data=ManageDeleteCallback(
                            stay_id=stay_id, page=page, filter_key=filter_key
                        ).pack(),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=i18n.t("manage.back_button"),
                        callback_data=ManageHistoryCallback(
                            page=page, filter_key=filter_key
                        ).pack(),
                    )
                ],
            ]
        )
        return MessageResult(message=message, keyboard=keyboard)

    async def get_stay_delete_confirmation(
        self,
        user: User,
        stay_id: int,
        page: int,
        filter_key: str,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        stay = await self._repo.get_by_id(stay_id)
        if stay is None or stay.telegram_id != user.telegram_id:
            return MessageResult(message=i18n.t("manage.stay_not_found"))

        parsed = _query_from_filter_key(filter_key)
        window = _date_window(parsed) if parsed is not None else None
        stay_text = self._format_history_stay(i18n, user, stay, window)
        message = f"{i18n.t('manage.confirm_delete_prompt')}\n\n{stay_text}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.t("manage.confirm_delete_button"),
                        callback_data=ManageConfirmDeleteCallback(
                            stay_id=stay_id, page=page, filter_key=filter_key
                        ).pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=i18n.t("manage.cancel_button"),
                        callback_data=ManageSelectCallback(
                            stay_id=stay_id, page=page, filter_key=filter_key
                        ).pack(),
                    )
                ],
            ]
        )
        return MessageResult(message=message, keyboard=keyboard)

    async def get_stay_edit_menu(
        self,
        user: User,
        stay_id: int,
        page: int,
        filter_key: str,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        stay = await self._repo.get_by_id(stay_id)
        if stay is None or stay.telegram_id != user.telegram_id:
            return MessageResult(message=i18n.t("manage.stay_not_found"))

        parsed = _query_from_filter_key(filter_key)
        window = _date_window(parsed) if parsed is not None else None
        stay_text = self._format_history_stay(i18n, user, stay, window)
        message = f"{stay_text}\n\n{i18n.t('manage.edit_prompt')}"

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.t("manage.country_field"),
                        callback_data=ManageEditFieldCallback(
                            stay_id=stay_id,
                            field="country",
                            page=page,
                            filter_key=filter_key,
                        ).pack(),
                    ),
                    InlineKeyboardButton(
                        text=i18n.t("manage.entry_date_field"),
                        callback_data=ManageEditFieldCallback(
                            stay_id=stay_id,
                            field="entry",
                            page=page,
                            filter_key=filter_key,
                        ).pack(),
                    ),
                    InlineKeyboardButton(
                        text=i18n.t("manage.exit_date_field"),
                        callback_data=ManageEditFieldCallback(
                            stay_id=stay_id,
                            field="exit",
                            page=page,
                            filter_key=filter_key,
                        ).pack(),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=i18n.t("manage.back_button"),
                        callback_data=ManageSelectCallback(
                            stay_id=stay_id, page=page, filter_key=filter_key
                        ).pack(),
                    )
                ],
            ]
        )
        return MessageResult(message=message, keyboard=keyboard)

    def get_edit_field_prompt(self, user: User, field: str) -> str:
        i18n = LocalizationService(user.language or "en")
        return i18n.t(f"manage.ask_{field}")

    async def history_for_query(
        self,
        user: User,
        query: ParsedHistoryCommand,
        *,
        page: int = 0,
    ) -> MessageResult:
        i18n = LocalizationService(user.language or "en")
        country_code: str | None = None
        country_name: str | None = None

        if query.country_input is not None:
            country = resolve_country(query.country_input)
            if country is None:
                return MessageResult(message=i18n.t("in.country_not_recognized"))
            country_code = country["code"]
            country_name = country["name"]

        window = _date_window(query)
        stays = await self._repo.list_by_user(user.telegram_id)
        filtered = [
            stay
            for stay in stays
            if _matches_history_filter(stay, country_code=country_code, window=window)
        ]
        filtered.sort(key=lambda stay: (stay.entry_date, stay.id or 0), reverse=True)

        if not filtered:
            return MessageResult(
                message=i18n.t("history.empty"),
                keyboard=self._history_keyboard(i18n, query, page=0, total=0),
            )

        total = len(filtered)
        safe_page = max(0, min(page, (total - 1) // HISTORY_PAGE_SIZE))
        start = safe_page * HISTORY_PAGE_SIZE
        end = min(start + HISTORY_PAGE_SIZE, total)
        page_stays = filtered[start:end]
        title = _history_title(i18n, query, country_name)

        parts = [
            i18n.t("history.header", title=title),
            i18n.t("history.showing", start=start + 1, end=end, total=total),
        ]
        for stay in page_stays:
            parts.extend(["", self._format_history_stay(i18n, user, stay, window)])

        message = "\n".join(parts)
        if len(message) > HISTORY_MESSAGE_LIMIT:
            message = message[: HISTORY_MESSAGE_LIMIT - 1].rstrip()
        return MessageResult(
            message=message,
            keyboard=self._history_keyboard(i18n, query, page=safe_page, total=total),
        )

    def _format_history_stay(
        self,
        i18n: LocalizationService,
        user: User,
        stay: Stay,
        window: tuple[date, date] | None,
    ) -> str:
        as_of = date.today()
        duration = _history_duration_days(stay, window, as_of=as_of)
        return i18n.t(
            "history.stay",
            flag=flag_emoji(stay.country_code),
            country=stay.country_name,
            entry_date=_format_history_date(stay.entry_date, user.date_format),
            exit_date=(
                i18n.t("stay.present")
                if stay.exit_date is None
                else _format_history_date(stay.exit_date, user.date_format)
            ),
            duration=format_duration_days(duration, i18n),
        )

    def _history_keyboard(
        self,
        i18n: LocalizationService,
        query: ParsedHistoryCommand,
        *,
        page: int,
        total: int,
    ) -> InlineKeyboardMarkup:
        filter_key = _filter_key(query)
        rows: list[list[InlineKeyboardButton]] = []
        page_buttons: list[InlineKeyboardButton] = []
        if page > 0:
            page_buttons.append(
                InlineKeyboardButton(
                    text=i18n.t("history.newer_button"),
                    callback_data=HistoryPageCallback(
                        page=page - 1,
                        filter_key=filter_key,
                    ).pack(),
                )
            )
        if (page + 1) * HISTORY_PAGE_SIZE < total:
            page_buttons.append(
                InlineKeyboardButton(
                    text=i18n.t("history.older_button"),
                    callback_data=HistoryPageCallback(
                        page=page + 1,
                        filter_key=filter_key,
                    ).pack(),
                )
            )
        if page_buttons:
            rows.append(page_buttons)

        current_year = date.today().year
        rows.append(
            [
                _filter_button(str(current_year), f"y{current_year}"),
                _filter_button(str(current_year - 1), f"y{current_year - 1}"),
                _filter_button(str(current_year - 2), f"y{current_year - 2}"),
            ]
        )
        rows.append(
            [
                _filter_button(
                    i18n.t("history.custom_dates_button"),
                    _custom_filter_key(filter_key),
                )
            ]
        )
        if total > 0:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=i18n.t("manage.manage_button"),
                        callback_data=ManageHistoryCallback(
                            page=page,
                            filter_key=filter_key,
                        ).pack(),
                    )
                ]
            )
        return InlineKeyboardMarkup(inline_keyboard=rows)


def _filter_button(text: str, filter_key: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text,
        callback_data=HistoryPageCallback(page=0, filter_key=filter_key).pack(),
    )


def _latest_open_stay(stays: list[Stay]) -> Stay | None:
    open_stays = [stay for stay in stays if stay.exit_date is None]
    if not open_stays:
        return None
    return max(open_stays, key=lambda stay: (stay.entry_date, stay.id or 0))


def _date_window(query: ParsedHistoryCommand) -> tuple[date, date] | None:
    if query.start_date is not None and query.end_date is not None:
        return query.start_date, query.end_date
    if query.year is not None:
        return date(query.year, 1, 1), date(query.year, 12, 31)
    return None


def _matches_history_filter(
    stay: Stay,
    *,
    country_code: str | None,
    window: tuple[date, date] | None,
) -> bool:
    if country_code is not None and stay.country_code != country_code:
        return False
    if window is None:
        return True
    stay_end = stay.exit_date if stay.exit_date is not None else window[1]
    return stay.entry_date <= window[1] and stay_end >= window[0]


def _history_duration_days(
    stay: Stay,
    window: tuple[date, date] | None,
    *,
    as_of: date,
) -> int:
    if window is None:
        return stay_duration_days(stay.entry_date, stay.exit_date, as_of=as_of)
    return days_in_range_within(
        stay.entry_date,
        stay.exit_date,
        window,
        cap=min(window[1], as_of) if stay.exit_date is None else window[1],
    )


def _history_title(
    i18n: LocalizationService,
    query: ParsedHistoryCommand,
    country_name: str | None,
) -> str:
    if query.start_date is not None and query.end_date is not None:
        title = i18n.t(
            "history.title_range",
            start=_format_history_date(query.start_date, DateFormat.DMY.value),
            end=_format_history_date(query.end_date, DateFormat.DMY.value),
        )
    elif query.year is not None:
        title = str(query.year)
    elif country_name is not None:
        title = country_name
    else:
        title = str(date.today().year)

    if country_name is not None and query.year is not None:
        return i18n.t(
            "history.title_country_year", country=country_name, year=query.year
        )
    if country_name is not None and query.start_date is not None:
        return i18n.t(
            "history.title_country_filter", country=country_name, filter=title
        )
    return title


def _filter_key(query: ParsedHistoryCommand) -> str:
    if query.country_input is not None and query.year is not None:
        country = resolve_country(query.country_input)
        code = country["code"] if country is not None else query.country_input
        return f"cy{code}-{query.year}"
    if query.country_input is not None:
        country = resolve_country(query.country_input)
        code = country["code"] if country is not None else query.country_input
        return f"c{code}"
    if query.start_date is not None and query.end_date is not None:
        return f"r{query.start_date.isoformat()}_{query.end_date.isoformat()}"
    if query.year is not None:
        return f"y{query.year}"
    return f"y{date.today().year}"


def _custom_filter_key(base_filter_key: str) -> str:
    return f"custom_{base_filter_key}"


def _custom_base_filter_key(filter_key: str) -> str | None:
    if filter_key == "custom":
        return f"y{date.today().year}"
    if filter_key.startswith("custom_"):
        return filter_key[7:]
    return None


def _merge_custom_date_range(
    base_query: ParsedHistoryCommand,
    range_query: ParsedHistoryCommand,
) -> ParsedHistoryCommand | None:
    if range_query.start_date is None or range_query.end_date is None:
        return base_query

    start = range_query.start_date
    end = range_query.end_date
    if base_query.year is not None:
        year_start = date(base_query.year, 1, 1)
        year_end = date(base_query.year, 12, 31)
        start = max(start, year_start)
        end = min(end, year_end)
        if end < start:
            return None

    return ParsedHistoryCommand(
        country_input=base_query.country_input,
        start_date=start,
        end_date=end,
    )


def _query_from_filter_key(filter_key: str) -> ParsedHistoryCommand | None:
    if filter_key == "custom":
        today = date.today()
        return ParsedHistoryCommand(year=today.year, current_year=True)
    if filter_key.startswith("cy"):
        value = filter_key[2:]
        if "-" not in value:
            return None
        country_code, raw_year = value.split("-", 1)
        if not raw_year.isdigit():
            return None
        return ParsedHistoryCommand(country_input=country_code, year=int(raw_year))
    if filter_key.startswith("c"):
        return ParsedHistoryCommand(country_input=filter_key[1:])
    if filter_key.startswith("r"):
        value = filter_key[1:]
        if "_" not in value:
            return None
        raw_start, raw_end = value.split("_", 1)
        try:
            start = date.fromisoformat(raw_start)
            end = date.fromisoformat(raw_end)
        except ValueError:
            return None
        if end < start:
            return None
        return ParsedHistoryCommand(start_date=start, end_date=end)
    if filter_key.startswith("y") and filter_key[1:].isdigit():
        return ParsedHistoryCommand(year=int(filter_key[1:]))
    return None


def _format_display_date(value: date, date_format: str | None) -> str:
    if date_format == DateFormat.MDY.value:
        return f"{value.strftime('%B')} {value.day}, {value.year}"
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _format_history_date(value: date, date_format: str | None) -> str:
    if date_format == DateFormat.MDY.value:
        return f"{value.strftime('%b')} {value.day}, {value.year}"
    return f"{value.day} {value.strftime('%b')} {value.year}"
