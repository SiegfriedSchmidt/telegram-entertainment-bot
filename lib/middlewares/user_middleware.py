from aiogram import BaseMiddleware
from aiogram.types import Message, User
from typing import Callable, Dict, Any, Awaitable
from lib import database
from lib.LLM.llm_providers import LLMProviders
from lib.temporal_storage import temporal_storage


class UserMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:
        user_data: User = data['event_from_user']
        providers: LLMProviders = data['providers']

        if temporal_storage.user_exists(user_data.id):
            user = temporal_storage.get_user(user_data.id)
        else:
            user = temporal_storage.add_user(user_data.id, user_data.username)
            database.create_user(user_data.id, user_data.username)

        data['user'] = user
        data['provider'] = providers[user.llm_provider]
        await handler(event, data)
