"""FSM for pending country-to-country transitions on /in."""

from aiogram.fsm.state import State, StatesGroup


class StayTransitionStates(StatesGroup):
    """User confirmed closing one country before entering another."""

    confirming = State()
    confirming_historical_exit = State()
