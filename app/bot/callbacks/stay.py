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
