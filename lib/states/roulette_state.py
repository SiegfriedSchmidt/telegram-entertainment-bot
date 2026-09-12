from aiogram.fsm.state import State, StatesGroup


class RouletteState(StatesGroup):
    roulette_activated = State()
