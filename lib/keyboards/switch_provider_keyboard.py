from lib.callbacks.switch_provider_callback import SwitchProviderCallback
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_switch_provider_keyboard(providers: list[str]):
    switch_provider_keyboard_builder = InlineKeyboardBuilder()

    for provider in providers:
        switch_provider_keyboard_builder.button(
            text=provider,
            callback_data=SwitchProviderCallback(provider=provider)
        )

    switch_provider_keyboard_builder.adjust(len(providers))
    return switch_provider_keyboard_builder.as_markup()
