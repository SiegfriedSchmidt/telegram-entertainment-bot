from collections.abc import Callable

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InputMediaPhoto
from lib.gambling.games.BlackjackGame import BlackjackGame
from lib.callbacks.blackjack_callback import BlackjackCallback
from lib.keyboards.blackjack_keyboard import get_blackjack_keyboard
from lib.middlewares.game_access_middleware import GameAccessMiddleware
from lib.states.blackjack_state import BlackjackState

ACTIONS: dict[str, Callable[[BlackjackGame], tuple[str, bool]]] = {
    "hit": BlackjackGame.hit,
    "stand": BlackjackGame.stand,
    "double": BlackjackGame.double,
    "split": BlackjackGame.split,
    "surrender": BlackjackGame.surrender,
}

CAPTIONS: dict[str, str] = {
    "hit": "Hit!",
    "stand": "Stand!",
    "double": "Double!",
    "split": "Split!",
    "surrender": "Surrender!",
}


def create_router():
    router = Router()
    router.message.filter(BlackjackState.blackjack_activated)
    router.callback_query.filter(BlackjackState.blackjack_activated)
    router.callback_query.middleware(GameAccessMiddleware())

    @router.callback_query(BlackjackCallback.filter(F.action.in_(list(ACTIONS))))
    async def play_cmd(callback: types.CallbackQuery, callback_data: BlackjackCallback, state: FSMContext):
        blackjack: BlackjackGame = (await state.get_data()).get("blackjack")
        action = callback_data.action
        filename, finished = ACTIONS[action](blackjack)

        image = FSInputFile(filename, filename=str(filename))
        if finished:
            media = InputMediaPhoto(media=image, caption=blackjack.get_caption_and_record_gain())
            await state.clear()
            return await callback.message.edit_media(media)

        media = InputMediaPhoto(media=image, caption=blackjack.get_active_hand_caption() + CAPTIONS[action])
        keyboard = get_blackjack_keyboard(blackjack.user.id, blackjack.get_available_actions())
        return await callback.message.edit_media(media, reply_markup=keyboard)

    @router.message(F.text.startswith("/"))
    async def command_cmd(message: types.Message, state: FSMContext):
        game_message: types.Message = (await state.get_data()).get("game_message")
        return await game_message.reply("You're playing blackjack right now!")

    return router
