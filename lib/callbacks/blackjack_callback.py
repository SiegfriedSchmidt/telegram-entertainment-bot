from aiogram.filters.callback_data import CallbackData


class BlackjackCallback(CallbackData, prefix="blackjack"):
    action: str
