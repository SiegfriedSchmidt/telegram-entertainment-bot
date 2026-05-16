from abc import ABC
from lib.ledger.ledger import Ledger
from lib.ledger.state_manager import FreezeHandle
from lib.models import MONEY_TYPE
from lib.temporal_storage import UserProfile


class BaseGame(ABC):
    MIN_BET: int = 0

    def __init__(self, ledger: Ledger, user: UserProfile, user_bet: MONEY_TYPE):
        self.ledger = ledger
        self.user = user
        self.user_bet = int(user_bet)
        self.gamble_bet, self.handle = self.process_bet()

    def process_bet(self) -> tuple[int, FreezeHandle]:
        if self.user_bet < self.MIN_BET:
            raise RuntimeError(f"Bet cannot be less than {self.MIN_BET}!")

        return self.ledger.calc_fee(self.user_bet)[0], self.ledger.freeze(self.user.id, self.user_bet)

    def get_balance_str(self) -> str:
        return f'{self.user}: {self.ledger.get_user_balance(self.user.id)} coins.'

    def finish_game(self, game_name: str, multiplier: float = None, raw_win_amount: int = None) -> None:
        if raw_win_amount is None and multiplier is None:
            raise RuntimeError("Win amount and multiplier cannot be None at the same time!")

        win_amount = raw_win_amount if raw_win_amount else int(multiplier * self.gamble_bet)
        net = win_amount - self.gamble_bet
        description = f"{game_name}" + (f" {multiplier}X" if multiplier is not None else "")

        self.handle.release()
        if win_amount == 0:
            self.ledger.record_deposit(
                from_user_id=self.user.id,
                amount=self.user_bet,
                description=description
            )
        elif net < 0:
            self.ledger.record_deposit(
                from_user_id=self.user.id,
                amount=-net,
                description=description,
                deduct_fee=False
            )
        elif net > 0:
            self.ledger.record_gain(
                to_user_id=self.user.id,
                amount=net,
                description=description
            )
