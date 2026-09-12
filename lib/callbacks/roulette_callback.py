from aiogram.filters.callback_data import CallbackData


class RouletteCallback(CallbackData, prefix="roulette"):
    action: str  # chip | bet | spin | clear
    target: str = ""  # the chip value, or the name of the spot that was tapped
    player_id: int
