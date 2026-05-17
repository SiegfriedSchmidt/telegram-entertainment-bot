from aiogram.filters.callback_data import CallbackData


class SwitchProviderCallback(CallbackData, prefix="switch"):
    provider: str
