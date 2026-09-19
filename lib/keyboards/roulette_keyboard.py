from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from lib.callbacks.roulette_callback import RouletteCallback
from lib.gambling.roulette import SPOTS, short_amount

CHIPS = [100, 500, 1000, 5000]  # every tap adds that much to the player's chip
OUTSIDE_SPOTS = ["1-18", "even", "red", "black", "odd", "19-36"]
DOZEN_SPOTS = ["1st12", "2nd12", "3rd12"]
COLUMN_SPOTS = ["col1", "col2", "col3"]


def get_roulette_keyboard(host_id: int, everyone_ready: bool = False):
    """The table as a keyboard: chips, 0, the 36 numbers, the outside bets, ready, SPIN and clear.

    No chip is marked as picked, because the keyboard belongs to the whole chat and every player
    has their own — the caption lists them instead. `host_id` only travels so that SPIN can tell
    who is allowed to press it. `everyone_ready` puts a target on it, so the host can see at a
    glance that nobody is still betting.
    """
    builder = InlineKeyboardBuilder()

    def button(text: str, action: str, target: str = "") -> InlineKeyboardButton:
        callback = RouletteCallback(action=action, target=target, player_id=host_id)
        return InlineKeyboardButton(text=text, callback_data=callback.pack())

    def spot(name: str) -> InlineKeyboardButton:
        return button(SPOTS[name].name, "bet", name)

    builder.row(*[button(f"+{short_amount(value)}", "chip", str(value)) for value in CHIPS],
                button(f"⟲{short_amount(CHIPS[0])}", "reset"))
    builder.row(button("0", "bet", "0"))
    for first in range(1, 37, 6):
        builder.row(*[spot(str(number)) for number in range(first, first + 6)])

    builder.row(*[spot(name) for name in OUTSIDE_SPOTS[:3]])
    builder.row(*[spot(name) for name in OUTSIDE_SPOTS[3:]])
    builder.row(*[spot(name) for name in DOZEN_SPOTS])
    builder.row(*[spot(name) for name in COLUMN_SPOTS])
    builder.row(button("SPIN 🎯" if everyone_ready else "SPIN", "spin"),
                button("👍 ready", "ready"), button("clear", "clear"))

    return builder.as_markup()
