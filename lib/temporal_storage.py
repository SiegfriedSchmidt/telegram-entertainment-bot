import random
from lib.models import UserModel


class TemporalStorage:
    def __init__(self):
        self._users: dict[int, UserModel] = dict()

    def get_user(self, user_id: int, user_username: str = '') -> UserModel:
        if user_id not in self._users:
            user = UserModel(
                username=user_username,
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
