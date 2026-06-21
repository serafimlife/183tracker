"""FSM states for history custom date filters and stay management editing."""

from aiogram.fsm.state import State, StatesGroup


class HistoryStates(StatesGroup):
    waiting_for_custom_range = State()


class HistoryManageStates(StatesGroup):
    editing_country = State()
    editing_entry_date = State()
    editing_exit_date = State()
