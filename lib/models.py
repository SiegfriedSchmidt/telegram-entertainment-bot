from pydantic import BaseModel, SecretStr
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


class RconModel(BaseModel):
    address: str
    port: str
    password: str
    rcon_logs_path: str


class HostModel(BaseModel):
    name: SecretStr
    hostname: SecretStr
    port: SecretStr
    username: SecretStr
    key_name: SecretStr
    docker_projects_path: str
    rcon: RconModel | None = None


class UserModel(BaseModel):
    username: str
    host: str
    nonce: int
    gamble_bet: int
    galton_bet: int
    blackjack_bet: int
    galton_balls: int
    galton_running_count: int


class TerminalType(str, BaseEnum):
    text = 'text'
    image = 'image'


class BlackjackResultType(str, BaseEnum):
    win = 'win'
    draw = 'draw'
    lose = 'lose'
    bust = 'bust'
    surrender = 'surrender'


class GainType(str, BaseEnum):
    big_jackpot = 'big_jackpot'
    jackpot = 'jackpot'
    nice_win = 'nice_win'
    loss = 'loss'


class StatsType(str, BaseEnum):
    prizes = 'prizes'
    mine = 'mine'
    gamble = 'gamble'
    galton = 'galton'
    blackjack_win = 'blackjack_win'
    blackjack_all = 'blackjack_all'
