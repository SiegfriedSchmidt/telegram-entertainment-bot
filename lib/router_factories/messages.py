from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import ReactionTypeEmoji
from lib.config_reader import config
from lib.gambling.games.SlotGame import SlotGame
from lib.ledger.ledger import Ledger
from lib.middlewares.user_middleware import UserMiddleware
from lib.states.confirmation_state import ConfirmationState
from lib.temporal_storage import UserProfile
from lib.utils.command_utils import download_video
from lib.utils.regex_utils import VIDEO_LINK_REGEX, get_video_link_from_text


def create_notifications_trigger(router: Router, notification_name: str, notification_id: int):
    @router.message(F.text.contains(notification_name))
    async def user_message(message: types.Message, state: FSMContext):
        await state.set_state(ConfirmationState.user_call_confirmation)
        await state.set_data({"notification_name": notification_name, "notification_id": notification_id})
        return await message.reply(
            f"Did someone say {notification_name}?! Calling {notification_name} will cost 1000$. (y/n)"
        )


def create_router():
    router = Router()
    router.message.middleware(UserMiddleware())

    for name, user_id in config.notification_ids.items():
        create_notifications_trigger(router, name, user_id)

    @router.message(ConfirmationState.user_call_confirmation)
    async def user_call(message: types.Message, state: FSMContext, ledger: Ledger, user: UserProfile):
        state_data = await state.get_data()
        notification_name: str = state_data["notification_name"]
        notification_id: int = state_data["notification_id"]
        await state.clear()
        if message.text.lower() == "y":
            ledger.record_transaction(user.id, notification_id, 1000, f"{notification_name} call")
            await message.bot.send_message(notification_id, f'{user} summoning you!')
            await message.react([ReactionTypeEmoji(emoji='👍')])
        else:
            await message.react([ReactionTypeEmoji(emoji='👎')])

    @router.message(F.text.lower().contains('bipki') | F.text.lower().contains('бипки'))
    async def bipki_message(message: types.Message):
        await message.react([ReactionTypeEmoji(emoji='🔥')])

    @router.message(F.text.lower().contains('docker') | F.text.lower().contains('докер') | (F.sticker.emoji == "🐳"))
    async def docker_message(message: types.Message):
        await message.react([ReactionTypeEmoji(emoji='🐳')])

    @router.message(F.text.lower().contains('repo') | F.text.lower().contains('репо'))
    async def repo_message(message: types.Message):
        await message.react([ReactionTypeEmoji(emoji='❤‍🔥')])

    @router.message(F.dice.emoji == "🎰")
    async def dice_message(message: types.Message, ledger: Ledger, user: UserProfile):
        await SlotGame(ledger, user).gamble(message)

    @router.message(F.text.regexp(VIDEO_LINK_REGEX))
    async def video_link_message(message: types.Message):
        link = get_video_link_from_text(message.text)
        await download_video(message, link, constraint=True)

    return router
