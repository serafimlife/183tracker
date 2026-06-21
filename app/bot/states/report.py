"""FSM state for report custom date filters."""

from aiogram.fsm.state import State, StatesGroup


class ReportStates(StatesGroup):
    waiting_for_custom_range = State()
