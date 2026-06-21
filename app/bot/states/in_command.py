"""FSM states for lightweight interactive `/in` argument collection."""

from aiogram.fsm.state import State, StatesGroup


class InCommandStates(StatesGroup):
    awaiting_country = State()
    awaiting_date = State()
