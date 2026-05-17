from lib.LLM.base import LLMProvider
from lib.LLM.dialog import Dialog
from openai import AsyncOpenAI
import aiohttp


class OpenAIProvider(LLMProvider):
    PROVIDER = "OpenAI"

    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__(api_key, model)
        self.base_url = base_url
        self.client = self.create_client()

    def create_client(self):
        return AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )

    def set_api_key(self, api_key: str):
        super().set_api_key(api_key)
        self.client = self.create_client()

    async def chat_complete(self, dialog: Dialog) -> str:
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=dialog.messages
        )

        return completion.choices[0].message.content

    async def check_limits(self) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(f'{self.base_url}/auth/key', headers=headers) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    return "Error"
