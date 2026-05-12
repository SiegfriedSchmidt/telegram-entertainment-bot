from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import ReactionTypeEmoji
from lib.config_reader import config
from lib.gambling.gambler import Gambler
from lib.ledger.ledger import Ledger
from lib.middlewares.user_middleware import UserMiddleware
from lib.states.confirmation_state import ConfirmationState
from lib.temporal_storage import temporal_storage
from lib.temporal_storage import UserProfile
from lib.utils.command_utils import download_video
from lib.utils.regex_utils import VIDEO_LINK_REGEX, get_video_link_from_text


def create_router():
    router = Router()
    router.message.middleware(UserMiddleware())

    @router.message(F.text.contains('admin'))
    async def admin_message(message: types.Message, state: FSMContext):
        await state.set_state(ConfirmationState.admin_call_confirmation)
        return await message.reply(f"Did someone say admin?! Calling admin will cost 1000$. (y/n)")

    @router.message(ConfirmationState.admin_call_confirmation)
    async def admin_call(message: types.Message, state: FSMContext, ledger: Ledger, user: UserProfile):
        await state.clear()
        if message.text.lower() == "y":
            for chat_id in config.notification_ids:
                to_user = temporal_storage.get_user(chat_id)
                ledger.record_transaction(user.id, to_user.id, 1000, "Admin call")
                await message.bot.send_message(chat_id, f'{user} summoning you!')
            await message.answer('fine')
        else:
            await message.answer('abort')

    @router.message(F.text.lower().contains('bipki') | F.text.lower().contains('бипки'))
    async def bipki_message(message: types.Message):
        await message.react([ReactionTypeEmoji(emoji='🔥')])

    @router.message(F.dice.emoji == "🎰")
    async def dice_message(message: types.Message, gambler: Gambler, user: UserProfile):
        await gambler.gamble(message, user)

    @router.message(F.text.regexp(VIDEO_LINK_REGEX))
    async def video_link_message(message: types.Message):
        link = get_video_link_from_text(message.text)
        await download_video(message, link)

    return router
