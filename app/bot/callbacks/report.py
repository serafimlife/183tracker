"""Callback data for report filter buttons."""

from aiogram.filters.callback_data import CallbackData


class ReportFilterCallback(CallbackData, prefix="rpt"):
    filter_key: str
