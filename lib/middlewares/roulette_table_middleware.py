from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from lib.gambling.games.RouletteGame import get_table


class RouletteTableMiddleware(BaseMiddleware):
    """Puts the open table of this chat into `data["table"]`.

    The guard the other games use checks that the tapper owns the game, which is the opposite of
    what a shared table wants — here anybody may take a seat. What is left to check is that the
    round is still open, so a tap on a finished one is answered instead of handled.
    """

    async def __call__(
            self,
            handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
            event: CallbackQuery,
            data: Dict[str, Any]
    ) -> Any:
        callback_data = data.get("callback_data")
        if callback_data is None:  # a button that is not ours
            return await handler(event, data)

        table = get_table(event.message.chat.id, callback_data.player_id)
        if table is None or table.settled:
            return await event.answer("This round is over.", show_alert=True, cache_time=3)
        if table.spinning:
            return await event.answer("The wheel is already spinning.", show_alert=True, cache_time=3)

        data["table"] = table
        return await handler(event, data)
