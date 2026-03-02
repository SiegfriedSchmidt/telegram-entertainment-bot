from enum import Enum, EnumMeta

from pydantic import BaseModel, SecretStr


class MetaEnum(EnumMeta):
    def __contains__(cls, item):
        try:
            cls(item)
        except ValueError:
            return False
        return True


class BaseEnum(Enum, metaclass=MetaEnum):
    pass


class HostModel(BaseModel):
    name: SecretStr
    hostname: SecretStr
    port: SecretStr
    username: SecretStr
    key_name: SecretStr


class UserModel(BaseModel):
    host: str
    nonce: int


class TerminalType(str, BaseEnum):
    text = 'text'
    image = 'image'


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
