"""FSM state groups for multi-step flows.

Onboarding is driven by inline callbacks; states gate which callbacks are accepted.
"""

from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    """Date format selection → done."""

    date_format = State()
