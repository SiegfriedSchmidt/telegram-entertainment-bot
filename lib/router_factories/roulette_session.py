import asyncio
from functools import partial
from aiogram import Router, types, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, InputMediaAnimation, InputMediaPhoto
from aiogram.utils.chat_action import ChatActionMiddleware
from lib.callbacks.roulette_callback import RouletteCallback
from lib.gambling.games.RouletteGame import (RouletteTable, find_table, get_table, open_table, parse_bets, tables_in)
from lib.gambling.roulette import SPOTS, render_roulette, short_amount
from lib.keyboards.roulette_keyboard import get_roulette_keyboard
from lib.ledger.ledger import Ledger
from lib.middlewares.roulette_table_middleware import RouletteTableMiddleware
from lib.middlewares.user_middleware import UserMiddleware
from lib.states.roulette_state import RouletteState
from lib.temporal_storage import UserProfile
from lib.workers import workers


async def show_table(message: types.Message, table: RouletteTable) -> bool:
    """Redraw the table. False when the tap changed nothing, which Telegram refuses to edit."""
    media = InputMediaPhoto(media=FSInputFile(table.table_image(), filename="roulette.png"),
                            caption=table.get_betting_caption(), parse_mode="HTML")
    try:
        await message.edit_media(media, reply_markup=get_roulette_keyboard(table.host.id, table.everyone_ready()))
        return True
    except TelegramBadRequest as error:
        if "not modified" not in str(error):
            raise
        return False


async def spin_table(message: types.Message, table: RouletteTable, state: FSMContext,
                     post: bool = False) -> None:
    """Draw the number, render the wheel, pay everyone out. SPIN and `-now` share this.

    `post` is `-now` on a table nobody has seen yet: the wheel goes out on its own instead of
    replacing the picture the players would have tapped on.
    """
    if not table.bets:
        await message.reply("Place at least one bet first.")
        return None

    # the number is drawn before the frames are, so the video cannot lie about the outcome
    number = table.draw_winning_number()
    filename, duration, _ = await workers.enqueue(partial(render_roulette, number, table.chips_on_table()))
    animation = FSInputFile(filename, filename=str(filename))

    if post:
        message = await message.reply_animation(animation)
    else:
        await message.edit_media(InputMediaAnimation(media=animation))
    await asyncio.sleep(duration)
    await message.edit_caption(caption=table.settle())
    return await state.clear()


def create_router() -> Router:
    """The whole of roulette: `/roulette`, `/bet`, and every tap on the table."""
    router = Router()
    router.callback_query.middleware(RouletteTableMiddleware())
    router.callback_query.middleware(UserMiddleware())
    router.message.middleware(ChatActionMiddleware())
    router.message.middleware(UserMiddleware())

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

    @router.callback_query(RouletteCallback.filter(F.action == "ready"))
    async def ready_cmd(callback: types.CallbackQuery, callback_data: RouletteCallback,
                        table: RouletteTable, user: UserProfile):
        """👍 — "I am done betting", so the host can see whose chips are still coming."""
        ready = table.toggle_ready(user)
        await show_table(callback.message, table)
        return await callback.answer("Ready 👍" if ready else "Bets open again")

    @router.callback_query(RouletteCallback.filter(F.action == "spin"))
    async def spin_cmd(callback: types.CallbackQuery, callback_data: RouletteCallback,
                       table: RouletteTable, user: UserProfile, state: FSMContext):
        if callback.from_user.id != callback_data.player_id:
            return await callback.answer("Only the host may spin the wheel", show_alert=True, cache_time=3)
        return await spin_table(callback.message, table, state)

    @router.message(Command("roulette"))
    async def roulette_cmd(message: types.Message, command: CommandObject, state: FSMContext,
                           user: UserProfile, ledger: Ledger):
        """`/roulette [chip] [amount spot ...] [-now] [-ready]` — open a table, and bet in one go."""
        chip, bets, now, ready = parse_bets(command.args.split() if command.args else [], user.roulette_bet)

        try:
            table = open_table(message.chat.id, ledger, user, chip)
        except RuntimeError as error:  # not enough coins to open a table
            return await message.reply(str(error))

        user.roulette_bet = chip
        try:
            table.place_bets(user, bets)  # "200 odd 100 red", straight from the command
        except RuntimeError as error:  # a chip below the minimum, or not enough coins
            return await message.reply(str(error))
        if ready:
            table.set_ready(user)  # after the bets: a chip put down takes the 👍 back

        if now:  # nobody is going to tap, so skip the table entirely
            return await spin_table(message, table, state, post=True)

        game_message = await message.reply_photo(
            FSInputFile(table.table_image(), filename="roulette.png"),
            caption=table.get_betting_caption(),
            reply_markup=get_roulette_keyboard(table.host.id),
            parse_mode="HTML"
        )
        table.message = game_message  # so /bet can find this wheel by a reply
        await state.set_state(RouletteState.roulette_activated)
        return await state.set_data({"game_message": game_message})

    @router.message(Command("bet"))
    async def bet_command_cmd(message: types.Message, command: CommandObject, state: FSMContext,
                              user: UserProfile):
        """Chips without touching the keyboard: `/bet 200 odd 100 red`.

        The table is the wheel you replied to, or your own, or the only one open in the chat.
        """
        args = command.args.split() if command.args else []
        if not args:
            return await message.reply("Tell me what to bet on: /bet 200 odd 100 red")

        chip, bets, now, ready = parse_bets(args)

        reply = message.reply_to_message
        table = find_table(message.chat.id, host_id=user.id, message_id=reply.message_id if reply is not None else None)
        if table is None:
            hint = "Reply to the wheel you mean." if tables_in(message.chat.id) else "No roulette is running."
            return await message.reply(hint)

        if now and user.id != table.host.id:
            return await message.reply("Only the host may spin the wheel.")

        try:
            if chip is not None:
                table.set_chip(user, chip)
            table.place_bets(user, bets)
        except RuntimeError as error:  # not enough coins, an unknown spot, a chip below the minimum
            return await message.reply(str(error))
        if ready:
            table.set_ready(user)  # `/bet -ready` with nothing else is fine too: just done

        if now:
            return await spin_table(table.message, table, state)

        if table.message is not None:
            await show_table(table.message, table)  # the picture already shows the stake
        return None

    @router.message(RouletteState.roulette_activated, F.text.startswith("/"))
    async def command_cmd(message: types.Message, state: FSMContext):
        if get_table(message.chat.id, message.from_user.id) is None:  # the round is over
            return await state.clear()
        game_message: types.Message = (await state.get_data()).get("game_message")
        return await game_message.reply("You're playing roulette right now!")

    return router
