"""The once-a-day wheel: everybody in the casino is on it, one of them takes the pot.

It runs from the job that updates the daily rewards, not from a command, and it is built *after*
the wheel has stopped — the way `DailySlotGame` is built after the dice roll.
"""
import random
from dataclasses import dataclass
from functools import partial

from lib.database import get_all_users
from lib.gambling.base import BaseGame
from lib.gambling.roulette import short_amount, render_daily_roulette
from lib.ledger.ledger import Ledger
from lib.temporal_storage import UserProfile, temporal_storage
from lib.workers import workers

DAILY_ROULETTE_PRIZE = 3000


@dataclass
class Participant:
    """One player on the daily wheel.

    `id` and the name it prints as are all `BaseGame` ever asks for, so a `Participant` stands in
    for a `UserProfile` when the prize is booked — and a real `UserProfile` works just as well.
    """

    id: int  # the id the ledger books the prize to
    name: str  # @username, or the id when there is none
    start: float = 0.0  # share of the rim, 0..1 — where their name is drawn
    end: float = 1.0

    def __str__(self):
        return self.name

    @property
    def slice(self) -> tuple[float, float]:
        """Its slice of the wheel, as angles in degrees — what the picture draws."""
        return self.start * 360.0, self.end * 360.0


@dataclass
class WheelOfFortuneResult:
    winner: Participant
    filename: str
    duration: float
    caption: str


def seat_everyone(users: list[tuple[int, str]]) -> list[Participant]:
    """Spread the whole casino over the wheel, from `get_all_users()` — `(id, name)` pairs.

    The shares are fractions rather than whole sectors, so everybody gets exactly 1/N of the rim
    however many of them there are, even when there are more players than there are sectors.
    """
    if not users:
        return []
    share = 1.0 / len(users)
    return [Participant(user_id, name, index * share, (index + 1) * share)
            for index, (user_id, name) in enumerate(users)]


async def spin_daily_roulette(ledger: Ledger) -> None | WheelOfFortuneResult:
    """Once a day: everybody is on the wheel, one of them takes the pot."""
    participants = seat_everyone(get_all_users())
    if not participants:
        return None

    winner, index = DailyRouletteGame.spin(participants)  # drawn before the frames are
    caption = DailyRouletteGame(ledger, temporal_storage.get_user(winner.id), DAILY_ROULETTE_PRIZE).pay()

    filename, duration, _ = await workers.enqueue(partial(render_daily_roulette, [p.name for p in participants], index))
    return WheelOfFortuneResult(winner, filename, duration, caption)


class DailyRouletteGame(BaseGame):
    MIN_BET = 0  # a prize, not a bet: nothing is frozen

    def __init__(self, ledger: Ledger, user: UserProfile, prize: int):
        super().__init__(ledger, user, 0)
        self.winner = Participant(id=user.id, name=str(user))
        self.prize = int(prize)

    def play(self):
        pass

    @staticmethod
    def spin(participants: list[Participant]) -> tuple[Participant, int]:
        """Pick the winner and the slice the ball stops on.

        The wheel is drawn with one equal slice per player, so a plain `randrange` is both exactly
        fair and exactly what the video will show — the ball cannot stop on anybody else's name.
        """
        if not participants:
            raise RuntimeError("Nobody to spin the daily roulette for!")

        index = random.randrange(len(participants))
        return participants[index], index

    def pay(self) -> str:
        """Book the prize and describe it, the way the other games caption a result."""
        self.finish_game("Daily roulette", raw_win_amount=self.prize)
        return f"🎉 {self.winner} wins the daily roulette! +{short_amount(self.prize)}!"
