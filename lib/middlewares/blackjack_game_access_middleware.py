from aiogram import BaseMiddleware
from aiogram.types import Message, User
from typing import Callable, Dict, Any, Awaitable
from lib.callbacks.blackjack_callback import BlackjackCallback


class BlackjackGameAccessMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:
        user_data: User = data['event_from_user']
        callback_data: BlackjackCallback = data['callback_data']

        if user_data.id != callback_data.player_id:
            return await event.answer(
                "This button belongs to another user •_•",
                show_alert=True,
                cache_time=3
            )

        return await handler(event, data)
