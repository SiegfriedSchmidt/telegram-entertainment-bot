from lib.LLM.base import LLMProvider
from lib.LLM.dialog import Dialog
import aiohttp

stream = False


# https://build.nvidia.com/moonshotai/kimi-k2.6/modelcard
class NvidiaProvider(LLMProvider):
    PROVIDER = "nvidia"

    def __init__(
            self, api_key, model="moonshotai/kimi-k2.6",
            invoke_url="https://integrate.api.nvidia.com/v1/chat/completions"
    ):
        self.invoke_url = invoke_url
        super().__init__(api_key, model)

    async def chat_complete(self, dialog: Dialog) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream" if stream else "application/json"
        }

        payload = {
            "model": self.model,
            "messages": dialog.messages,
            "max_tokens": 16384,
            "temperature": 1.00,
            "top_p": 1.00,
            "stream": stream,
            "chat_template_kwargs": {"thinking": False},
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.invoke_url, headers=headers, json=payload) as resp:
                data = await resp.json()
                return data["choices"][0]["message"]["content"]

    async def check_limits(self) -> str:
        pass
