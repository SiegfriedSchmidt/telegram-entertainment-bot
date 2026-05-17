from pydantic import SecretStr
from lib.LLM.base import LLMProvider
from lib.LLM.providers.google_provider import GoogleProvider
from lib.LLM.providers.nvidia_provider import NvidiaProvider
from lib.LLM.providers.openrouter_provider import OpenrouterProvider


class LLMProviders:
    def __init__(self, providers_credentials: dict[str, SecretStr], proxy_url=''):
        self.__providers: dict[str, LLMProvider] = dict()
        for provider_name, provider_secret_api_key in providers_credentials.items():
            provider_api_key = provider_secret_api_key.get_secret_value()
            match provider_name:
                case OpenrouterProvider.PROVIDER:
                    self.__providers[OpenrouterProvider.PROVIDER] = OpenrouterProvider(provider_api_key)
                case GoogleProvider.PROVIDER:
                    self.__providers[GoogleProvider.PROVIDER] = GoogleProvider(provider_api_key, proxy_url=proxy_url)
                case NvidiaProvider.PROVIDER:
                    self.__providers[NvidiaProvider.PROVIDER] = NvidiaProvider(provider_api_key)
                case _:
                    raise RuntimeError(f"Unknown provider: {provider_name}")

    def __getitem__(self, item: str) -> LLMProvider:
        return self.__providers[item]

    def __contains__(self, item: str) -> bool:
        return item in self.__providers

    def names(self) -> list[str]:
        return list(self.__providers.keys())
