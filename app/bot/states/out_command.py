"""FSM states for lightweight interactive `/out` argument collection."""

from aiogram.fsm.state import State, StatesGroup


class OutCommandStates(StatesGroup):
    awaiting_country = State()
    awaiting_date = State()
