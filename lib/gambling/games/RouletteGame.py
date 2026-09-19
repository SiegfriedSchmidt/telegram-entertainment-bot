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
        if amount is None:
            amount = self.chip
        elif str(amount) == "allin":
            amount = self.ledger.get_user_balance(self.user.id)
        else:
            amount = int(amount)

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
        self.message = None  # the picture the round lives on, set by /roulette
        self.ready: set[int] = set()  # the players who said they are done betting
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
        """Every player picks their own chip, so two of them never fight over the size.

        The chip is a number or `allin` (the whole balance); anything else is refused, the way
        `process_bet` refuses it. A chip below the minimum is raised to it, so nobody gets stuck
        with a bet they are not allowed to place.
        """
        if str(chip) == "allin":
            amount = int(self.ledger.get_user_balance(user.id))
        elif str(chip).isdigit():
            amount = int(chip)
        else:
            raise RuntimeError(f"Invalid bet {chip}")  # the wording base.py uses

        self.chips[user.id] = max(amount, RouletteGame.MIN_BET)
        self.seat(user).chip = self.chips[user.id]
        return self.chips[user.id]

    def add_chip(self, user: UserProfile, amount: MONEY_TYPE) -> int:
        """Raise the chip the player is betting with, so any bet can be built up from the minimum."""
        return self.set_chip(user, self.chip_of(user) + int(amount))

    def reset_chip(self, user: UserProfile) -> int:
        """Back to the smallest chip, after a misclick."""
        return self.set_chip(user, RouletteGame.MIN_BET)

    def chip_of(self, user: UserProfile) -> int:
        """The chip the player bets with; the minimum until they pick another one."""
        return self.chips.get(user.id, RouletteGame.MIN_BET)

    def stake_of(self, user: UserProfile) -> int:
        return self.seats[user.id].stake if user.id in self.seats else 0

    # ------------------------------------------------------------------- betting
    def place_bet(self, user: UserProfile, spot: Spot, amount: MONEY_TYPE = None) -> Bet:
        self.ready.discard(user.id)  # still putting chips down, so not ready any more
        return self.seat(user).place_bet(spot, amount if amount is not None else self.chip_of(user))

    def place_bets(self, user: UserProfile, bets: list[tuple[str, int]]) -> None:
        """Several chips at once, the way `/roulette 200 odd 100 red` asks for them."""
        for name, amount in bets:
            self.place_bet(user, SPOTS[name], amount)

    def clear_bets(self, user: UserProfile) -> None:
        self.ready.discard(user.id)
        self.seat(user).clear_bets()

    # --------------------------------------------------------------------- ready
    def set_ready(self, user: UserProfile, ready: bool = True) -> None:
        """A player says they are done betting — and takes it back with the same button."""
        if ready:
            self.ready.add(user.id)
        else:
            self.ready.discard(user.id)

    def toggle_ready(self, user: UserProfile) -> bool:
        self.set_ready(user, user.id not in self.ready)
        return user.id in self.ready

    def everyone_ready(self) -> bool:
        """Nobody with a chip down is still betting. The host does not count — they spin."""
        guests = {bet.user.id for bet in self.bets} - {self.host.id}
        return bool(guests) and guests <= self.ready

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
        close_table(self.chat_id, self.host.id)
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
            ready = " 👍" if user.id in self.ready else ""
            caption.append(f"{seat.dot} {user}{host}: chip {short_amount(self.chip_of(user))}"
                           f" · staked {short_amount(seat.stake)}{ready}")
        if len(self.seats) > 1:
            caption.append("Everybody is ready — spin when you like." if self.everyone_ready()
                           else f"Only {self.host} can spin the wheel.")
        return "\n".join(caption)


def parse_bets(args: list[str], chip: MONEY_TYPE = None) -> tuple[MONEY_TYPE, list[tuple[str, int]], bool]:
    """Read `/roulette 200 odd 100 red -now` into the chip to start with, the bets, and whether to
    spin at once.

    A lone word in front is the chip — that is how `/roulette 1000` and `/roulette allin` keep
    working — the rest are `amount spot` pairs, and `-now` can sit anywhere.
    """
    tokens = [token for token in args if token != "-now"]
    spin_now = "-now" in args

    if len(tokens) % 2 and tokens[0].lower() not in SPOTS:
        chip, tokens = tokens[0], tokens[1:]

    bets = []
    for amount, name in zip(tokens[::2], tokens[1::2]):
        if name.lower() not in SPOTS or not (str(amount).isdigit() or str(amount) == "allin"):
            raise RuntimeError(f"Invalid bet {amount} {name}")
        bets.append((name.lower(), amount))

    if len(tokens) % 2:
        raise RuntimeError(f"Invalid bet {tokens[-1]}")
    return chip, bets, spin_now


TABLES: dict[tuple[int, int], RouletteTable] = {}  # (chat id, host id) -> that player's open round
TABLE_TIMEOUT = 10 * 60  # a table whose host never spins frees itself eventually


def open_table(chat_id: int, ledger: Ledger, user: UserProfile, chip: MONEY_TYPE = None) -> RouletteTable:
    """Open a round — or, when this player already has one open here, sit back down at it.

    Two players in the same chat each get their own table: whoever opens a round is its host, and
    the only one who may spin it.
    """
    chip = chip if chip is not None else user.roulette_bet
    table = TABLES.get((chat_id, user.id))
    if table is None or table.settled or time.time() - table.started_at > TABLE_TIMEOUT:
        if ledger.get_user_balance(user.id) < RouletteGame.MIN_BET:
            raise RuntimeError(f"You need at least {RouletteGame.MIN_BET} coins to open a table!")
        table = TABLES[chat_id, user.id] = RouletteTable(chat_id, user, ledger, chip)
    else:
        table.set_chip(user, chip)
    return table


def get_table(chat_id: int, host_id: int) -> RouletteTable | None:
    return TABLES.get((chat_id, host_id))


def tables_in(chat_id: int) -> list[RouletteTable]:
    """Every round still open in this chat — several players can run their own at once."""
    return [table for (chat, _), table in TABLES.items() if chat == chat_id and not table.settled]


def find_table(chat_id: int, host_id: int = None, message_id: int = None) -> RouletteTable | None:
    """The round a `/bet` means: the wheel being replied to, then the player's own, then the only
    one open in the chat.
    """
    open_tables = tables_in(chat_id)
    for table in open_tables:
        if message_id is not None and table.message is not None and table.message.message_id == message_id:
            return table
    for table in open_tables:
        if host_id is not None and table.host.id == host_id:
            return table
    return open_tables[0] if len(open_tables) == 1 else None


def close_table(chat_id: int, host_id: int) -> None:
    TABLES.pop((chat_id, host_id), None)
