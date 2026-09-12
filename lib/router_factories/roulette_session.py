import asyncio
from functools import partial

from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InputMediaAnimation, InputMediaPhoto

from lib.callbacks.roulette_callback import RouletteCallback
from lib.gambling.games.RouletteGame import RouletteTable, get_table
from lib.gambling.roulette import SPOTS, render_roulette, short_amount
from lib.keyboards.roulette_keyboard import get_roulette_keyboard
from lib.middlewares.roulette_table_middleware import RouletteTableMiddleware
from lib.middlewares.user_middleware import UserMiddleware
from lib.states.roulette_state import RouletteState
from lib.temporal_storage import UserProfile
from lib.workers import workers


async def show_table(message: types.Message, table: RouletteTable) -> bool:
    """Redraw the table. False when the tap changed nothing, which Telegram refuses to edit."""
    image = FSInputFile(table.table_image(), filename="roulette.png")
    media = InputMediaPhoto(media=image, caption=table.get_betting_caption(), parse_mode="HTML")
    try:
        await message.edit_media(media, reply_markup=get_roulette_keyboard(table.host.id))
        return True
    except TelegramBadRequest as error:
        if "not modified" not in str(error):
            raise
        return False


def create_router() -> Router:
    """Every tap on the table. The /roulette command itself lives with your other commands (NOTES)."""
    router = Router()
    router.callback_query.middleware(RouletteTableMiddleware())
    router.callback_query.middleware(UserMiddleware())

    @router.callback_query(RouletteCallback.filter(F.action == "chip"))
    async def chip_cmd(callback: types.CallbackQuery, callback_data: RouletteCallback,
                       table: RouletteTable, user: UserProfile):
        chip = table.add_chip(user, callback_data.target)
        await show_table(callback.message, table)
        return await callback.answer(f"chip: {short_amount(chip)}")

    @router.callback_query(RouletteCallback.filter(F.action == "reset"))
    async def reset_cmd(callback: types.CallbackQuery, callback_data: RouletteCallback,
                        table: RouletteTable, user: UserProfile):
        chip = table.reset_chip(user)
        await show_table(callback.message, table)
        return await callback.answer(f"chip: {short_amount(chip)}")

    @router.callback_query(RouletteCallback.filter(F.action == "bet"))
    async def bet_cmd(callback: types.CallbackQuery, callback_data: RouletteCallback,
                      table: RouletteTable, user: UserProfile):
        try:
            table.place_bet(user, SPOTS[callback_data.target])
        except RuntimeError as error:  # a chip below the minimum, or not enough coins
            return await callback.answer(str(error), show_alert=True, cache_time=3)

        await show_table(callback.message, table)
        return await callback.answer()

    @router.callback_query(RouletteCallback.filter(F.action == "clear"))
    async def clear_cmd(callback: types.CallbackQuery, callback_data: RouletteCallback,
                        table: RouletteTable, user: UserProfile):
        table.clear_bets(user)  # only the chips of whoever pressed the button
        if not await show_table(callback.message, table):
            return await callback.answer("Nothing to clear")
        return await callback.answer()

    @router.callback_query(RouletteCallback.filter(F.action == "spin"))
    async def spin_cmd(callback: types.CallbackQuery, callback_data: RouletteCallback,
                       table: RouletteTable, user: UserProfile, state: FSMContext):
        if callback.from_user.id != callback_data.player_id:
            return await callback.answer("Only the host may spin the wheel", show_alert=True, cache_time=3)
        if not table.bets:
            return await callback.answer("Place at least one bet first", show_alert=True, cache_time=3)

        # the number is drawn before the frames are, so the video cannot lie about the outcome
        number = table.draw_winning_number()
        filename, duration, _ = await workers.enqueue(partial(render_roulette, number, table.chips_on_table()))

        await callback.message.edit_media(InputMediaAnimation(media=FSInputFile(filename, filename=str(filename))))
        await asyncio.sleep(duration)
        await callback.message.edit_caption(caption=table.settle())
        return await state.clear()

    @router.message(RouletteState.roulette_activated, F.text.startswith("/"))
    async def command_cmd(message: types.Message, state: FSMContext):
        if get_table(message.chat.id) is None:  # the round is over, stop holding the player
            return await state.clear()
        return await message.reply("You're playing roulette right now!")

    return router
