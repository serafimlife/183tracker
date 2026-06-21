"""Callback data for history pagination, filters, and stay management."""

from aiogram.filters.callback_data import CallbackData


class HistoryPageCallback(CallbackData, prefix="hist"):
    page: int
    filter_key: str


class ManageHistoryCallback(CallbackData, prefix="hist_mgmt"):
    """Open stay-selection screen for the current history page."""

    page: int
    filter_key: str


class ManageSelectCallback(CallbackData, prefix="mgmt_sel"):
    """User tapped a numbered button to pick a stay."""

    stay_id: int
    page: int
    filter_key: str


class ManageDeleteCallback(CallbackData, prefix="mgmt_del"):
    """Show delete-confirmation screen for a stay."""

    stay_id: int
    page: int
    filter_key: str


class ManageConfirmDeleteCallback(CallbackData, prefix="mgmt_cfd"):
    """User confirmed deletion of a stay."""

    stay_id: int
    page: int
    filter_key: str


class ManageEditMenuCallback(CallbackData, prefix="mgmt_em"):
    """Open field-selection edit menu for a stay."""

    stay_id: int
    page: int
    filter_key: str


class ManageEditFieldCallback(CallbackData, prefix="mgmt_ef"):
    """User chose a field to edit; field is 'country', 'entry', or 'exit'."""

    stay_id: int
    field: str
    page: int
    filter_key: str
