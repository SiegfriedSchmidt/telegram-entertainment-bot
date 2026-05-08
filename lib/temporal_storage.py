import random
from lib.models import UserModel
from lib.utils.general_utils import get_name


class UserProfile(UserModel):
    def __str__(self) -> str:
        return get_name(self.username, self.id)


class TemporalStorage:
    def __init__(self):
        self._users: dict[int, UserProfile] = dict()

    def add_user(self, user_id: int, username: str = None) -> UserProfile:
        user = UserProfile(
            id=user_id,
            username=username,
            nonce=random.randint(1, 1000),
            gamble_bet=100,
            blackjack_bet=100,
            galton_bet=100,
            galton_balls=1,
            galton_running_count=0
        )
        self._users[user_id] = user
        return user

    def user_exists(self, user_id: int) -> bool:
        return user_id in self._users

    def get_user(self, user_id: int) -> UserProfile:
        if not self.user_exists(user_id):
            raise RuntimeError(f'User id {user_id} does not exist!')
        return self._users[user_id]


temporal_storage = TemporalStorage()
