from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InputMediaPhoto
from lib.blackjack import Blackjack
from lib.callbacks.blackjack_callback import BlackjackCallback
from lib.keyboards.blackjack_keyboard import blackjack_keyboard_builder
from lib.models import BlackjackResultType
from lib.states.blackjack_state import BlackjackState


def create_router():
    router = Router()
    router.message.filter(BlackjackState.blackjack_activated)
    router.callback_query.filter(BlackjackState.blackjack_activated)

    @router.callback_query(BlackjackCallback.filter(F.action == "hit"))
    async def hit_cmd(callback: types.CallbackQuery, state: FSMContext):
        blackjack: Blackjack = (await state.get_data()).get("blackjack")
        filename, lose = blackjack.hit()

        image = FSInputFile(filename, filename=str(filename))
        media = InputMediaPhoto(media=image, caption="Hit!")
        if lose:
            media.caption = blackjack.get_caption_and_record_gain(BlackjackResultType.bust)
            await state.clear()

        return await callback.message.edit_media(media, reply_markup=blackjack_keyboard_builder.as_markup())

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
        caption = blackjack.get_caption_and_record_gain(BlackjackResultType.surrender)
        await state.clear()

        return await callback.message.edit_caption(caption=caption)

    @router.message(F.text.startswith("/"))
    async def command_cmd(message: types.Message):
        return await message.answer("You're playing blackjack right now!")

    return router
