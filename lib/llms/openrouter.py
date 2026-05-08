import aiohttp
from openai import AsyncOpenAI
from pydantic import SecretStr
from lib.asyncio_workers import AsyncioWorkers
from lib.llms.general_llm import LLM, Dialog


class OpenrouterLLM(LLM):
    def __init__(self, api_key: SecretStr, workers: AsyncioWorkers, model="x-ai/grok-4.20-multi-agent"):
        super().__init__(api_key, workers, model)
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
        )

    async def _chat_complete(self, dialog: Dialog) -> str:
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
            async with session.get('https://openrouter.ai/api/v1/auth/key', headers=headers) as resp:
                if resp.status == 200:
                    return await resp.text()
                else:
                    return "Error"
