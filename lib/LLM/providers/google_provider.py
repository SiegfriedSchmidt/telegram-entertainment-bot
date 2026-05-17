from lib.LLM.base import LLMProvider
from lib.LLM.dialog import Dialog
from google import genai
from google.genai import types


# https://github.com/googleapis/python-genai
class GoogleProvider(LLMProvider):
    PROVIDER = "google"

    def __init__(self, api_key: str, model="gemini-2.5-flash", proxy_url=''):
        super().__init__(api_key, model)
        self.client = self.create_client(proxy_url)

    def create_client(self, proxy_url=''):
        http_options = types.HttpOptions(
            client_args={'proxy': proxy_url},
            async_client_args={'proxy': proxy_url},
        ) if proxy_url else None

        return genai.Client(
            api_key=self.api_key,
            http_options=http_options
        ).aio

    def set_api_key(self, api_key: str):
        super().set_api_key(api_key)
        self.client = self.create_client()

    async def chat_complete(self, dialog: Dialog) -> str:
        response = await self.client.models.generate_content(
            model=self.model,
            contents=dialog.stringify(include_system=False),
            config=types.GenerateContentConfig(
                system_instruction=dialog.get_system_message()
            ),
        )
        return response.text

    async def check_limits(self) -> str:
        return "Not implemented"
