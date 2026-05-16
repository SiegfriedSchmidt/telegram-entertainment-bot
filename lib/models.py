from pydantic import BaseModel
from enum import Enum, EnumMeta


class MetaEnum(EnumMeta):
    def __contains__(cls, item):
        try:
            cls(item)
        except ValueError:
            return False
        return True


class BaseEnum(Enum, metaclass=MetaEnum):
    pass


MONEY_TYPE = int | str | float


class UserModel(BaseModel):
    id: int
    username: str | None
    nonce: int
    slot_bet: int
    galton_bet: int
    blackjack_bet: int
    galton_balls: int
    galton_running_count: int


class BlackjackResultType(str, BaseEnum):
    win = 'win'
    draw = 'draw'
    lose = 'lose'
    bust = 'bust'
    surrender = 'surrender'


class SlotResultType(str, BaseEnum):
    big_jackpot = 'big_jackpot'
    jackpot = 'jackpot'
    nice_win = 'nice_win'
    loss = 'loss'


class StatsType(str, BaseEnum):
    prizes = 'prizes'
    mine = 'mine'
    slot = 'slot'
    galton = 'galton'
    blackjack_win = 'blackjack_win'
    blackjack_all = 'blackjack_all'
