from typing import Optional

from lib.models import UserModel
from lib.ssh_manager import ssh_manager
from lib.config_reader import config


class User:
    def __init__(self, user: Optional[UserModel] = None):
        self.__user = UserModel(
            host=config.main_host.get_secret_value(),
            nonce=1
        ) if user is None else user

    @property
    def nonce(self) -> int:
        return self.__user.nonce

    @nonce.setter
    def nonce(self, new_nonce: int):
        self.__user.nonce = new_nonce

    @property
    def host(self) -> str:
        return self.__user.host

    @host.setter
    def host(self, new_host: str):
        if new_host not in ssh_manager.get_hosts():
            raise KeyError(f'Host {new_host} does not exist!')
        self.__user.host = new_host


class TemporalStorage:
    def __init__(self):
        self._users: dict[int, User] = dict()

    def get_user(self, user_id: int) -> User:
        if user_id not in self._users:
            self._users[user_id] = User()
        return self._users[user_id]


temporal_storage = TemporalStorage()
