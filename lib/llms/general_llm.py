from abc import ABC, abstractmethod
from pydantic import SecretStr


class Dialog:
    def __init__(self):
        self.messages = []

    def add_user_message(self, message):
        self.messages.append({
            "role": "user",
            "content": message
        })

    def add_assistant_message(self, message):
        self.messages.append({
            "role": "assistant",
            "content": message
        })

    def pop_message(self):
        self.messages.pop()

    def __str__(self):
        str_dialog = ''
        for message in self.messages:
            str_dialog += f'---{message["role"]}---: {message["content"]}\n'
        return str_dialog


class LLM(ABC):
    def __init__(self, api_key: SecretStr, model: str):
        self.api_key = api_key.get_secret_value()
        self.model = model

    @abstractmethod
    async def chat_complete(self, dialog: Dialog) -> str:
        ...

    @abstractmethod
    async def check_limits(self) -> str:
        ...

    def __str__(self):
        return f'model: {self.model}\napi_key: {self.api_key[0:15]}.....{self.api_key[-5:]}\n'
