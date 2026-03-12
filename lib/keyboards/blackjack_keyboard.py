from lib.callbacks.blackjack_callback import BlackjackCallback
from aiogram.utils.keyboard import InlineKeyboardBuilder


def get_blackjack_keyboard(player: str):
    blackjack_keyboard_builder = InlineKeyboardBuilder()

    for action in ["hit", "stand", "surrender"]:
        blackjack_keyboard_builder.button(
            text=action,
            callback_data=BlackjackCallback(action=action, player=player)
        )

    blackjack_keyboard_builder.adjust(3)
    return blackjack_keyboard_builder.as_markup()
