"""Tests for /report aggregation and filtering."""

from datetime import date
from unittest.mock import AsyncMock

import pytest

import app.services.report_service as report_mod
from app.models.stay import Stay
from app.models.user import User
from app.services.filters import TimelineFilter
from app.services.report_service import (
    ReportService,
    _report_duration_days,
    _report_window,
)
from app.utils.formatters import get_threshold_indicator


class FixedDate(date):
    @classmethod
    def today(cls) -> date:
        return cls(2026, 5, 30)


def _user(telegram_id: int = 100) -> User:
    return User(
        telegram_id=telegram_id,
        username="tester",
        first_name="Test",
        language="en",
        date_format="dmy",
    )


def _stay(
    stay_id: int,
    telegram_id: int = 100,
    *,
    entry: str,
    exit: str | None = None,
    code: str = "TH",
    name: str = "Thailand",
) -> Stay:
    return Stay(
        id=stay_id,
        telegram_id=telegram_id,
        country_code=code,
        country_name=name,
        entry_date=date.fromisoformat(entry),
        exit_date=date.fromisoformat(exit) if exit else None,
    )


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_mod, "date", FixedDate)


class TestReportDuration:
    """Unit tests for _report_duration_days — window-aware day counting."""

    def test_full_stay_no_window(self) -> None:
        stay = _stay(1, entry="2026-01-01", exit="2026-01-10")
        assert _report_duration_days(stay, window=None) == 10

    def test_active_stay_no_window_uses_today(self) -> None:
        stay = _stay(1, entry="2026-05-01")
        # FixedDate.today() = 2026-05-30, so 1 May to 30 May inclusive = 30 days
        assert _report_duration_days(stay, window=None) == 30

    def test_overlap_inside_window(self) -> None:
        stay = _stay(1, entry="2026-03-10", exit="2026-03-12")
        window = (date(2026, 3, 1), date(2026, 7, 5))
        assert _report_duration_days(stay, window) == 3

    def test_overlap_partial_at_start(self) -> None:
        stay = _stay(1, entry="2026-02-25", exit="2026-05-16")
        window = (date(2026, 3, 1), date(2026, 7, 5))
        assert _report_duration_days(stay, window) == 77

    def test_overlap_partial_at_end(self) -> None:
        stay = _stay(1, entry="2026-06-20", exit="2026-07-10")
        window = (date(2026, 3, 1), date(2026, 7, 5))
        assert _report_duration_days(stay, window) == 16

    def test_overlap_active_stay_capped_to_today(self) -> None:
        """Active stay with window in the future — only days up to today count."""
        stay = _stay(1, entry="2026-05-01")
        window = (date(2026, 5, 15), date(2026, 6, 15))
        # FixedDate.today() = 2026-05-30
        # overlap: 15 May to 30 May inclusive = 16 days
        assert _report_duration_days(stay, window) == 16

    def test_no_overlap_outside_window(self) -> None:
        stay = _stay(1, entry="2025-04-01", exit="2025-04-10")
        window = (date(2026, 1, 1), date(2026, 12, 31))
        assert _report_duration_days(stay, window) == 0

    # --- Active stay regression tests ---

    def test_active_stay_in_filtered_year_capped_to_today(self) -> None:
        """Active stay within a filtered year must not count future days."""
        stay = _stay(1, entry="2026-05-17")  # no exit
        window = (date(2026, 1, 1), date(2026, 12, 31))
        # FixedDate.today() = 2026-05-30
        # correct: 17 May to 30 May inclusive = 14 days
        assert _report_duration_days(stay, window) == 14

    def test_active_stay_crossing_year_boundary(self) -> None:
        """Active stay starting before filter year caps to today, not year-end."""
        stay = _stay(1, entry="2025-12-25")  # no exit
        window = (date(2026, 1, 1), date(2026, 12, 31))
        # FixedDate.today() = 2026-05-30
        # overlap: 1 Jan to 30 May inclusive = 150 days
        assert _report_duration_days(stay, window) == 150

    def test_active_stay_no_window_clips_to_today(self) -> None:
        """Active stay without filter — always cap to today."""
        stay = _stay(1, entry="2026-05-17")
        # FixedDate.today() = 2026-05-30
        assert _report_duration_days(stay, window=None) == 14


class TestReportWindow:
    """Unit tests for _report_window — filter to date range."""

    def test_year_window(self) -> None:
        result = _report_window(TimelineFilter(year=2026))
        assert result == (date(2026, 1, 1), date(2026, 12, 31))

    def test_no_filter(self) -> None:
        assert _report_window(TimelineFilter()) is None

    def test_custom_date_range(self) -> None:
        flt = TimelineFilter(start_date=date(2026, 3, 1), end_date=date(2026, 7, 5))
        result = _report_window(flt)
        assert result == (date(2026, 3, 1), date(2026, 7, 5))

    def test_empty_filter_no_window(self) -> None:
        assert _report_window(TimelineFilter()) is None

    def test_current_year_only(self) -> None:
        assert _report_window(TimelineFilter(current_year=True)) is None

    def test_year_and_current_year(self) -> None:
        result = _report_window(TimelineFilter(year=2026, current_year=True))
        assert result == (date(2026, 1, 1), date(2026, 12, 31))


class TestReportService:
    """Integration tests for ReportService."""

    @pytest.fixture
    def service(self) -> ReportService:
        session = AsyncMock()
        svc = ReportService(session)
        svc._repo = AsyncMock()
        return svc

    async def test_empty_report(self, service: ReportService) -> None:
        user = _user()
        service._repo.list_by_user.return_value = []

        result = await service.handle_report_command(user, TimelineFilter())

        assert "No data for this period." in result.message

    async def test_aggregation_multiple_countries(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-10"),
            _stay(
                2, entry="2026-02-01", exit="2026-02-05", code="ID", name="Indonesia"
            ),
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        assert "🇹🇭 Thailand" in result.message
        assert "🇮🇩 Indonesia" in result.message
        assert "10 days" in result.message
        assert "5 days" in result.message

    async def test_sorting_descending(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-02-01", exit="2026-03-01"),  # TH: 29 days
            _stay(
                2, entry="2026-01-01", exit="2026-01-10", code="ID", name="Indonesia"
            ),  # ID: 10 days
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        th_pos = result.message.index("🇹🇭")
        id_pos = result.message.index("🇮🇩")
        assert th_pos < id_pos

    async def test_year_filter(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2025-06-01", exit="2025-06-10"),  # excluded
            _stay(2, entry="2026-03-01", exit="2026-03-05"),  # 5 days
        ]

        result = await service.handle_report_command(user, TimelineFilter(year=2026))

        assert "5 days" in result.message
        assert "10 days" not in result.message

    async def test_overlap_at_year_boundary(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2025-12-25", exit="2026-01-10"),
        ]

        result = await service.handle_report_command(user, TimelineFilter(year=2026))

        # 1 Jan 2026 - 10 Jan 2026 inclusive = 10 days
        assert "10 days" in result.message

    async def test_country_filter(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-10"),
            _stay(
                2, entry="2026-01-15", exit="2026-01-20", code="ID", name="Indonesia"
            ),
        ]

        result = await service.handle_report_command(
            user, TimelineFilter(country_input="Indonesia")
        )

        assert "Indonesia" in result.message
        assert "Thailand" not in result.message

    async def test_unrecognized_country(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = []

        result = await service.handle_report_command(
            user, TimelineFilter(country_input="Atlantis")
        )

        assert result.message.startswith("❌")
        assert "not recognized" in result.message

    async def test_report_has_year_and_custom_filter_buttons(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-10"),
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        assert result.keyboard is not None
        rows = result.keyboard.inline_keyboard
        assert [button.text for button in rows[0]] == ["2026", "2025", "2024"]
        assert rows[1][0].text == "Custom Dates"

    async def test_report_custom_dates_callback_prompts(self, service) -> None:
        user = _user()

        result = await service.handle_report_callback(user, "custom_y2026")

        assert result.message.startswith("Send custom date range.")
        assert result.fsm_data == {"report_base_filter_key": "y2026"}

    async def test_report_custom_date_range_valid(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-03-15", exit="2026-03-20", code="ID", name="Indonesia")
        ]

        result = await service.handle_custom_date_range(user, "01.03.26 05.07.26")

        assert "Residency Report" in result.message
        assert "1 Mar 2026–5 Jul 2026" in result.message
        assert "Indonesia" in result.message

    async def test_report_custom_range_header_overrides_base_year(
        self, service
    ) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-03"),
        ]

        result = await service.handle_custom_date_range(
            user,
            "01.01.26 01.06.26",
            base_filter_key="y2024",
        )

        assert "Residency Report — 1 Jan 2026–1 Jun 2026" in result.message
        assert "Residency Report — 2024" not in result.message


class TestReportThresholds:
    """Tests for threshold and rolling info in /report output."""

    @pytest.fixture
    def service(self) -> ReportService:
        session = AsyncMock()
        svc = ReportService(session)
        svc._repo = AsyncMock()
        return svc

    async def test_rolling_and_threshold_lines_present(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-10"),
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        assert "Days in selected period: 10 days" in result.message
        assert "Rolling 365:" in result.message
        assert "Remaining before 183-day calendar threshold:" in result.message
        assert "Remaining before 183-day rolling threshold:" in result.message

    async def test_threshold_indicators_are_correct(self, service) -> None:
        user = _user()
        # 2026-01-01 to 2026-01-10 = 10 period days
        # rolling 365 from FixedDate.today()=2026-05-30: 10 days in window 2025-05-31..2026-05-30
        # calendar remaining = 183 - 10 = 173, indicator = 🟢 (> 60)
        # rolling remaining = 183 - 10 = 173, indicator = 🟢
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-10"),
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        assert get_threshold_indicator(173) in result.message
        assert "173 days" in result.message

    async def test_threshold_indicator_yellow(self, service) -> None:
        user = _user()
        # stay from 2026-01-01 to 2026-04-01 = 91 period days
        # calendar remaining = 183 - 91 = 92 → 🟢 (> 60)
        # Use more days to get into yellow range
        # stay from 2025-10-01 to 2026-04-30 = lots of overlap in rolling window
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2025-10-01", exit="2026-04-30"),
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        # period days = 1 Jan to 30 Apr 2026 = 120 days (for year 2026)
        # calendar remaining = 183 - 120 = 63 → 🟢 (> 60)
        # rolling window 2025-05-31 to 2026-05-30: overlap with 2025-10-01..2026-04-30 = 212 days
        # rolling remaining = 183 - 212 = 0 (capped) → 🔴 (<= 30)
        assert get_threshold_indicator(0) in result.message

    async def test_multi_country_formatting(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-10"),
            _stay(
                2, entry="2026-02-01", exit="2026-02-05", code="ID", name="Indonesia"
            ),
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        # Thailand should come first (10 days > 5 days)
        th_pos = result.message.index("🇹🇭")
        id_pos = result.message.index("🇮🇩")
        assert th_pos < id_pos

        # Each country block has threshold info
        assert result.message.count("Remaining before 183-day calendar threshold:") == 2

    async def test_threshold_with_year_filter(self, service) -> None:
        user = _user()
        # 2025 stay should be excluded from period but included in rolling 365
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2025-12-20", exit="2025-12-25"),  # 0 in 2026 period
            _stay(2, entry="2026-03-01", exit="2026-03-05"),
        ]

        result = await service.handle_report_command(user, TimelineFilter(year=2026))

        # 5 period days, calendar remaining = 178
        assert "5 days" in result.message
        assert "178 days" in result.message

    async def test_threshold_with_country_filter(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-01-01", exit="2026-01-10"),
            _stay(
                2, entry="2026-02-01", exit="2026-02-05", code="ID", name="Indonesia"
            ),
        ]

        result = await service.handle_report_command(
            user, TimelineFilter(country_input="Indonesia")
        )

        assert "Indonesia" in result.message
        assert "Thailand" not in result.message
        # Only one country block
        assert result.message.count("Remaining before 183-day calendar threshold:") == 1

    async def test_empty_report_still_works(self, service) -> None:
        user = _user()
        service._repo.list_by_user.return_value = []

        result = await service.handle_report_command(user, TimelineFilter())

        assert "No data for this period." in result.message

    async def test_active_stay_no_future_days_in_rolling(self, service) -> None:
        user = _user()
        # Active stay starting 2026-05-17, no exit
        # FixedDate.today() = 2026-05-30
        # Period days (no filter) = 14 days (17 May to 30 May inclusive)
        # Rolling 365: window 2025-05-31 to 2026-05-30, overlap = 14 days
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2026-05-17"),
        ]

        result = await service.handle_report_command(user, TimelineFilter())

        assert "14 days" in result.message

    async def test_rolling_window_independent_of_year_filter(self, service) -> None:
        """Rolling 365 must include stays outside the filtered year."""
        user = _user()
        # FixedDate.today() = 2026-05-30
        # Rolling window: 2025-05-31 to 2026-05-30
        # Stay 1 (2025-10-01 to 2025-10-10): 10 rolling days, 0 period days (outside 2026)
        # Stay 2 (2026-03-01 to 2026-03-05): 5 rolling days, 5 period days
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2025-10-01", exit="2025-10-10"),
            _stay(2, entry="2026-03-01", exit="2026-03-05"),
        ]

        result = await service.handle_report_command(user, TimelineFilter(year=2026))

        assert "Days in selected period: 5 days" in result.message
        assert "Rolling 365: 15 days" in result.message

    async def test_rolling_across_years_with_active_stay(self, service) -> None:
        """Active + fully-outside-year stays: rolling counts both."""
        user = _user()
        # FixedDate.today() = 2026-05-30
        # Rolling window: 2025-05-31 to 2026-05-30
        # Stay 1 (2025-08-20 to 2025-09-05): 17 rolling, 0 period (outside 2026)
        # Stay 2 (2026-05-17, active): 14 rolling + period
        service._repo.list_by_user.return_value = [
            _stay(1, entry="2025-08-20", exit="2025-09-05"),
            _stay(2, entry="2026-05-17"),
        ]

        result = await service.handle_report_command(user, TimelineFilter(year=2026))

        assert "Days in selected period: 14 days" in result.message
        assert "Rolling 365: 31 days" in result.message
