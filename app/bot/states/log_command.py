"""FSM states for interactive `/log` stay creation."""

from aiogram.fsm.state import State, StatesGroup


class LogCommandStates(StatesGroup):
    awaiting_country = State()
    awaiting_entry_date = State()
    awaiting_exit_date = State()
