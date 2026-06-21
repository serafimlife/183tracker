"""Callback data for stay management actions."""

from aiogram.filters.callback_data import CallbackData


class RemoveStayCallback(CallbackData, prefix="rm_stay"):
    """Only stay_id is sent; ownership is verified server-side."""

    stay_id: int


class ConfirmTransitionCallback(CallbackData, prefix="tr_yes"):
    """Open stay to close; pending new country/date live in FSM storage."""

    stay_id: int


class CancelTransitionCallback(CallbackData, prefix="tr_no"):
    """Cancel pending transition (no payload)."""


class ConfirmHistoricalExitCallback(CallbackData, prefix="hx_yes"):
    """Historical stay to close; inferred exit date lives in FSM storage."""

    stay_id: int


class AnotherHistoricalExitCallback(CallbackData, prefix="hx_other"):
    """User will provide historical exit manually with /out."""

    stay_id: int


class KeepHistoricalOpenCallback(CallbackData, prefix="hx_open"):
    """User chooses to keep the historical stay open."""

    stay_id: int
