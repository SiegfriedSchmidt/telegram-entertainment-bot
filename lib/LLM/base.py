from lib.LLM.dialog import Dialog
from abc import ABC, abstractmethod


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
