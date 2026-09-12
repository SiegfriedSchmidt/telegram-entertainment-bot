import random
import time
from dataclasses import dataclass

import cv2

from lib.gambling.base import BaseGame
from lib.gambling.roulette import (ROULETTE_NUMBERS, SPOTS, Spot, describe_number, player_colour,
                                   player_dot, render_table, short_amount)
from lib.init import tmp_folder_path
from lib.ledger.ledger import Ledger
from lib.ledger.state_manager import FreezeHandle
from lib.models import MONEY_TYPE
from lib.temporal_storage import UserProfile


@dataclass
class Bet:
    user: UserProfile  # every chip knows its owner — that is the whole trick
    spot: Spot
    amount: int  # stake as the player sees it
    gamble_amount: int  # stake after fees, payouts are counted from it
    handle: FreezeHandle


class RouletteGame(BaseGame):
    """One player's round: their chips, their stake, their payout.

    A table holds one of these per player, so `finish_game` keeps booking to a single user and
    nothing in `base.py` has to know that a table can be shared.
    """

    MIN_BET = 100

    def __init__(self, ledger: Ledger, user: UserProfile, chip: MONEY_TYPE = None, colour: int = 0):
        self.ledger = ledger
        self.user = user
        self.chip = int(chip) if chip else int(user.roulette_bet)
        self.colour, self.dot = player_colour(colour), player_dot(colour)
        self.user_bet = self.gamble_bet = 0  # nothing is frozen until the first chip is down
        self.handles: list[FreezeHandle] = []
        self.bets: list[Bet] = []
        self.winning_number: int | None = None

    def play(self):
        pass

    # ------------------------------------------------------------------- betting
    def place_bet(self, spot: Spot, amount: MONEY_TYPE = None) -> Bet:
        """Put one chip down. The stake is frozen at once, like in every other game."""
        amount = self.chip if amount is None else int(amount)
        if amount < self.MIN_BET:
            raise RuntimeError(f"Bet cannot be less than {self.MIN_BET}!")
        if self.ledger.get_user_balance(self.user.id) < amount:
            raise RuntimeError("Not enough coins for that chip!")

        bet = Bet(self.user, spot, amount, self.add_bet(amount), self.handles[-1])
        self.bets.append(bet)
        return bet

    def clear_bets(self) -> None:
        """Take this player's chips back off the table."""
        for bet in self.bets:
            bet.handle.release()
            self.handles.remove(bet.handle)
            self.user_bet -= bet.amount
            self.gamble_bet -= bet.gamble_amount
        self.bets = []

    @property
    def stake(self) -> int:
        return self.user_bet

    # --------------------------------------------------------------------- spin
    def settle(self, winning_number: int) -> str:
        """Pay this player out and return their line of the result caption."""
        won = [bet for bet in self.bets if winning_number in bet.spot.numbers]
        win_amount = sum(bet.gamble_amount * bet.spot.payout for bet in won)
        multiplier = round(win_amount / self.gamble_bet, 2) if self.gamble_bet else 0
        self.finish_game("Roulette", multiplier, raw_win_amount=int(win_amount))

        if won:
            outcome = "Won " + ", ".join(f"{bet.spot.name} X{bet.spot.payout}" for bet in won)
        else:
            outcome = "Lost " + ", ".join(bet.spot.name for bet in self.bets)
        return f"{self.dot} {outcome} → X{multiplier:g}! {self.get_balance_str()}"


class RouletteTable:
    """One round: one wheel, one table, as many players as care to sit down.

    Whoever runs /roulette owns the wheel and is the only one allowed to spin it; anybody in the
    chat may put chips down, each with their own chip size, and every one of them is paid apart.
    """

    def __init__(self, chat_id: int, host: UserProfile, ledger: Ledger, chip: MONEY_TYPE = None):
        self.chat_id, self.host, self.ledger = chat_id, host, ledger
        self.seats: dict[int, RouletteGame] = {}  # user id -> that player's round
        self.chips: dict[int, int] = {}  # user id -> the chip size they picked
        self.winning_number: int | None = None
        self.settled = False
        self.started_at = time.time()
        self.set_chip(host, chip if chip is not None else host.roulette_bet)

    # ------------------------------------------------------------------ seating
    def seat(self, user: UserProfile) -> RouletteGame:
        """The player's round, opened with their first chip. Colours follow the seating order."""
        if user.id not in self.seats:
            self.seats[user.id] = RouletteGame(self.ledger, user, self.chip_of(user), len(self.seats))
        return self.seats[user.id]

    def players(self) -> list[UserProfile]:
        return [game.user for game in self.seats.values()]

    def set_chip(self, user: UserProfile, chip: MONEY_TYPE) -> int:
        """Every player picks their own chip, so two of them never fight over the size."""
        self.chips[user.id] = int(chip) if str(chip).isdigit() else int(user.roulette_bet)
        self.seat(user).chip = self.chips[user.id]
        return self.chips[user.id]

    def chip_of(self, user: UserProfile) -> int:
        return self.chips.get(user.id, int(user.roulette_bet))

    def stake_of(self, user: UserProfile) -> int:
        return self.seats[user.id].stake if user.id in self.seats else 0

    # ------------------------------------------------------------------- betting
    def place_bet(self, user: UserProfile, spot: Spot) -> Bet:
        return self.seat(user).place_bet(spot, self.chip_of(user))

    def clear_bets(self, user: UserProfile) -> None:
        self.seat(user).clear_bets()

    @property
    def bets(self) -> list[Bet]:
        return [bet for game in self.seats.values() for bet in game.bets]

    @property
    def spinning(self) -> bool:
        """The number is drawn but not paid yet: the wheel is turning, no more bets."""
        return self.winning_number is not None and not self.settled

    # ---------------------------------------------------------------------- spin
    def draw_winning_number(self) -> int:
        self.winning_number = random.choice(ROULETTE_NUMBERS)
        return self.winning_number

    def settle(self) -> str:
        """Pay every player and close the table. One line per player, in seating order."""
        caption = [f"{self.winning_number}, {describe_number(self.winning_number)}."]
        caption += [game.settle(self.winning_number) for game in self.seats.values() if game.bets]
        self.settled = True
        close_table(self.chat_id)
        return "\n".join(caption)

    # ----------------------------------------------------------------- rendering
    def chips_on_table(self) -> list[tuple[str, int, tuple]]:
        """`(spot, amount, colour)` for every chip, ready to be drawn on the table."""
        return [(bet.spot.name, bet.amount, self.seats[bet.user.id].colour) for bet in self.bets]

    def table_image(self) -> str:
        image = render_table(self.chips_on_table(), wheel=True)
        filename = tmp_folder_path / f"roulette_{random.randint(0, 1 << 31)}.png"
        cv2.imwrite(filename, image)
        return filename

    def get_betting_caption(self) -> str:
        caption = ["<b>Roulette</b> — the bets are open, tap a spot to put a chip down."]
        for user in self.players():
            seat = self.seats[user.id]
            host = " (host)" if user.id == self.host.id else ""
            caption.append(f"{seat.dot} {user}{host}: chip {short_amount(self.chip_of(user))}"
                           f" · staked {short_amount(seat.stake)}")
        if len(self.seats) > 1:
            caption.append(f"Only {self.host} can spin the wheel.")
        return "\n".join(caption)


TABLES: dict[int, RouletteTable] = {}  # chat id -> the open round, one per chat
TABLE_TIMEOUT = 10 * 60  # a table whose host never spins frees itself eventually


def open_table(chat_id: int, ledger: Ledger, user: UserProfile, chip: MONEY_TYPE = None) -> RouletteTable:
    """Open a round in this chat — or, when one is already open, take a seat at it."""
    table = TABLES.get(chat_id)
    if table is None or table.settled or time.time() - table.started_at > TABLE_TIMEOUT:
        if ledger.get_user_balance(user.id) < RouletteGame.MIN_BET:
            raise RuntimeError(f"You need at least {RouletteGame.MIN_BET} coins to open a table!")
        table = TABLES[chat_id] = RouletteTable(chat_id, user, ledger, chip)
    elif chip is not None:
        table.set_chip(user, chip)
    return table


def get_table(chat_id: int) -> RouletteTable | None:
    return TABLES.get(chat_id)


def close_table(chat_id: int) -> None:
    TABLES.pop(chat_id, None)
