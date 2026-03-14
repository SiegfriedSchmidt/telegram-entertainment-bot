import random
from pydantic import field_validator
from lib.models import UserModel
from lib.ssh_manager import ssh_manager
from lib.config_reader import config


class User(UserModel, validate_assignment=True):
    @field_validator('host', mode='before')
    @classmethod
    def validate_host(cls, value: str):
        if value not in ssh_manager.get_hosts():
            raise KeyError(f'Host {value} does not exist!')
        return value


class TemporalStorage:
    def __init__(self):
        self._users: dict[int, User] = dict()

    def get_user(self, user_id: int, user_username: str = '') -> User:
        if user_id not in self._users:
            user = User(
                username=user_username,
                host=config.main_host.get_secret_value(),
                nonce=random.randint(1, 1000),
                gamble_bet=100,
                blackjack_bet=100,
                galton_bet=100,
                galton_balls=1,
                galton_running_count=0
            )
            if user_username:
                self._users[user_id] = user
        else:
            user = self._users[user_id]

        return user


temporal_storage = TemporalStorage()
