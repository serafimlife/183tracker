"""FSM states for file import."""

from aiogram.fsm.state import State, StatesGroup


class ImportStates(StatesGroup):
    awaiting_date_format = State()
    awaiting_file = State()
