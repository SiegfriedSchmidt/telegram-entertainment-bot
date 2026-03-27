from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InputMediaPhoto
from lib.blackjack import Blackjack
from lib.callbacks.blackjack_callback import BlackjackCallback
from lib.keyboards.blackjack_keyboard import get_blackjack_keyboard
from lib.middlewares.blackjack_game_access_middleware import BlackjackGameAccessMiddleware
from lib.models import BlackjackResultType
from lib.states.blackjack_state import BlackjackState


def create_router():
    router = Router()
    router.message.filter(BlackjackState.blackjack_activated)
    router.callback_query.filter(BlackjackState.blackjack_activated)
    router.callback_query.middleware(BlackjackGameAccessMiddleware())

    @router.callback_query(BlackjackCallback.filter(F.action == "hit"))
    async def hit_cmd(callback: types.CallbackQuery, state: FSMContext):
        blackjack: Blackjack = (await state.get_data()).get("blackjack")
        filename, lose = blackjack.hit()

        image = FSInputFile(filename, filename=str(filename))
        media = InputMediaPhoto(media=image, caption="Hit!")
        if lose:
            media.caption = blackjack.get_caption_and_record_gain(BlackjackResultType.bust)
            await state.clear()
            return await callback.message.edit_media(media)

        return await callback.message.edit_media(media, reply_markup=get_blackjack_keyboard(blackjack.username))

    @router.callback_query(BlackjackCallback.filter(F.action == "stand"))
    async def stand_cmd(callback: types.CallbackQuery, state: FSMContext):
        blackjack: Blackjack = (await state.get_data()).get("blackjack")
        filename, result = blackjack.stand()
        caption = blackjack.get_caption_and_record_gain(result)

        image = FSInputFile(filename, filename=str(filename))
        media = InputMediaPhoto(media=image, caption=caption)
        await state.clear()

        return await callback.message.edit_media(media)

    @router.callback_query(BlackjackCallback.filter(F.action == "surrender"))
    async def surrender_cmd(callback: types.CallbackQuery, state: FSMContext):
        blackjack: Blackjack = (await state.get_data()).get("blackjack")
        filename = blackjack.surrender()
        caption = blackjack.get_caption_and_record_gain(BlackjackResultType.surrender)

        image = FSInputFile(filename, filename=str(filename))
        media = InputMediaPhoto(media=image, caption=caption)
        await state.clear()

        return await callback.message.edit_media(media)

    @router.message(F.text.startswith("/"))
    async def command_cmd(message: types.Message, state: FSMContext):
        game_message: types.Message = (await state.get_data()).get("game_message")
        return await game_message.reply("You're playing blackjack right now!")

    return router
