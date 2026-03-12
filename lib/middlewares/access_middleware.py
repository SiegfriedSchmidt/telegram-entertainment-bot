from aiogram import BaseMiddleware
from aiogram.types import Message, User
from typing import Callable, Dict, Any, Awaitable
from aiogram.dispatcher.flags import get_flag
from lib.config_reader import config
from lib.otp_manager import otp_manager


class AccessMiddleware(BaseMiddleware):
    async def __call__(
            self,
            handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
            event: Message,
            data: Dict[str, Any]
    ) -> Any:
        user_data: User = data['event_from_user']
        otp_required = get_flag(data, 'otp')

        if otp_required and not otp_manager.is_authenticated(user_data.id) and user_data.id not in config.admin_ids:
            return await event.answer('<b>Permission denied</b>.', parse_mode="html")

        return await handler(event, data)
