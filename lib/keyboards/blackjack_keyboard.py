from lib.callbacks.blackjack_callback import BlackjackCallback
from aiogram.utils.keyboard import InlineKeyboardBuilder

blackjack_keyboard_builder = InlineKeyboardBuilder()

for action in ["hit", "stand", "surrender"]:
    blackjack_keyboard_builder.button(
        text=action,
        callback_data=BlackjackCallback(action=action)
    )

blackjack_keyboard_builder.adjust(3)
