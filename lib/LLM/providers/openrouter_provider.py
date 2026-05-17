from lib.LLM.openai_base import OpenAIProvider


class OpenrouterProvider(OpenAIProvider):
    PROVIDER = "openrouter"

    def __init__(self, api_key: str, model="x-ai/grok-4.20-multi-agent"):
        super().__init__("https://openrouter.ai/api/v1", api_key, model)
