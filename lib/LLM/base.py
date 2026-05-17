from abc import ABC, abstractmethod


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


class LLMProvider(ABC):
    PROVIDER: str = ""

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def set_api_key(self, api_key: str):
        self.api_key = api_key

    def set_model(self, model: str):
        self.model = model

    async def ask(self, text: str):
        dialog = Dialog()
        dialog.add_user_message(text)
        return await self.chat_complete(dialog)

    @abstractmethod
    async def chat_complete(self, dialog: Dialog) -> str:
        ...

    @abstractmethod
    async def check_limits(self) -> str:
        ...

    def __str__(self):
        return (
            f'provider: {self.PROVIDER}\n'
            f'model: {self.model}\n'
            f'api_key: {self.api_key[0:15]}.....{self.api_key[-5:]}\n'
        )
