import asyncio
import random
from itertools import chain
from pathlib import Path
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, FSInputFile
from aiogram.utils.chat_action import ChatActionMiddleware
from lib import database
from lib.blackjack import Blackjack
from lib.bot_commands import text_bot_general_commands, text_bot_admin_commands
from lib.config_reader import config
from lib.init import galton_backgrounds_folder_path
from lib.keyboards.blackjack_keyboard import get_blackjack_keyboard
from lib.ledger import Ledger, BlockNotMined
from lib.api.gemini_api import gemini_api
from lib.api.joke_api import get_joke
from lib.api.meme_api import get_meme
from lib.api.geoip_api import geoip
from lib.gambler import Gambler
from lib.middlewares.user_middleware import UserMiddleware
from lib.physics_simulation import PhysicsSimulation
from lib.states.blackjack_state import BlackjackState
from lib.states.confirmation_state import ConfirmationState
from lib.storage import storage
from lib.temporal_storage import User
from lib.utils.utils import get_args, large_respond, is_bot_admin


def create_router():
    router = Router()
    router.message.middleware(ChatActionMiddleware())
    router.message.middleware(UserMiddleware())

    @router.message(Command("h"))
    async def h_cmd(message: types.Message):
        if message.from_user.id in config.admin_ids:
            await message.answer(text_bot_admin_commands)
        else:
            await message.answer(text_bot_general_commands)

    @router.message(Command("joke"))
    async def joke_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 0, 1)

        try:
            joke_type = args[0] if len(args) == 1 else None
            joke = await get_joke(joke_type)
        except Exception as e:
            return await message.answer(str(e))
        return await message.answer(joke)

    @router.message(Command("meme"))
    async def meme_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 0, 1)

        try:
            meme_subreddit = args[0] if len(args) == 1 else None
            url, caption = await get_meme(meme_subreddit)
        except Exception as e:
            return await message.answer(str(e))

        try:
            if url.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                await message.answer_photo(url, caption=caption)
            elif url.endswith('.gif'):
                await message.answer_animation(url, caption=caption)
            elif url.endswith(('.mp4', '.gifv', '.webm')):
                await message.answer_video(url, caption=caption)
        except TelegramBadRequest:
            await asyncio.sleep(1)
            await message.answer(f"{url}\n\n{caption}", disable_web_page_preview=False)

        return None

    @router.message(Command("ask"))
    async def ask_cmd(message: types.Message, command: CommandObject):
        args = command.args
        if not args:
            return await message.answer("You need to specify a query.")

        answer = await message.answer('asking...')
        response = await gemini_api.ask(args)
        await large_respond(message, response)
        return await answer.delete()

    @router.message(Command("geoip"))
    async def geoip_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 1, 1)

        try:
            json = await geoip(args[0])
            text = '\n'.join(f"{key}: {val}" for key, val in json.items())
        except Exception as e:
            return await message.answer(str(e))
        return await message.answer(text)

    @router.message(Command("niggachain"))
    async def chain_cmd(message: types.Message):
        return await message.answer('https://www.youtube-nocookie.com/embed/8V1eO0Ztuis')

    @router.message(Command("gamble"))
    async def gamble_cmd(message: types.Message, command: CommandObject, gambler: Gambler, user: User):
        args = get_args(command, 0, 1)
        bet = args[0] if len(args) == 1 else None
        return await gambler.gamble(message, user, bet)

    @router.message(Command("galton"))
    async def galton_cmd(message: types.Message, command: CommandObject, gambler: Gambler, user: User):
        args = get_args(command, 0, 2)
        bet = args[0] if len(args) >= 1 else None
        balls = args[1] if len(args) == 2 else ('1' if len(args) == 1 else None)
        return await gambler.galton(message, user, bet, balls)

    @router.message(Command("blackjack"))
    async def blackjack_cmd(message: types.Message, command: CommandObject, state: FSMContext, user: User,
                            ledger: Ledger):
        args = get_args(command, 0, 1)
        bet = args[0] if len(args) == 1 else user.blackjack_bet

        blackjack = Blackjack(ledger, user.username, bet)
        filename = blackjack.start()
        image = FSInputFile(filename, filename=str(filename))
        user.blackjack_bet = bet

        game_message = await message.reply_photo(
            image,
            caption=f"Blackjack, bet: <b>{bet}</b>.",
            reply_markup=get_blackjack_keyboard(user.username),
            parse_mode="HTML"
        )

        await state.set_state(BlackjackState.blackjack_activated)
        return await state.set_data({"blackjack": blackjack, "game_message": game_message})

    @router.message(Command("balance"))
    async def balance_cmd(message: types.Message, ledger: Ledger):
        return await message.answer(f"Your balance is {ledger.get_user_balance(message.from_user.username)}.")

    @router.message(Command("transfer"))
    async def transfer_cmd(message: types.Message, command: CommandObject, state: FSMContext, ledger: Ledger):
        args = get_args(command, 0, 2)
        if message.reply_to_message:
            to_user = message.reply_to_message.from_user.username
            if len(args) == 1 and args[0].isdecimal():
                amount = args[0]
            else:
                return await message.answer('Correct amount is required!')
        elif len(args) == 2 and args[0].isdecimal():
            amount = args[0]
            to_user = args[1]
        elif len(args) == 2 and args[1].isdecimal():
            amount = args[1]
            to_user = args[0]
        else:
            return await message.answer('Invalid syntax!')

        to_user = to_user.replace("@", "").strip()
        from_user = message.from_user.username
        if from_user == to_user:
            return await message.answer("You can't transfer to yourself!")

        me = await message.bot.me()
        is_user_me = to_user == me.username
        if is_user_me or not database.is_user_exists(to_user):
            await state.set_state(ConfirmationState.transfer_confirmation)
            await state.set_data({"to_user": to_user, "amount": amount})
            return await message.answer(
                f"Are you sure you want to transfer {amount} to {'me 👉👈' if is_user_me else 'nonexistent user'} (y/n)?"
            )

        ledger.record_transaction(from_user, to_user, amount, "transfer")
        return await message.answer(f"Successfully transferred {amount} to {to_user}!")

    @router.message(ConfirmationState.transfer_confirmation)
    async def transfer(message: types.Message, state: FSMContext, ledger: Ledger):
        if message.text.lower() == "y":
            state_data = await state.get_data()
            to_user, amount = state_data["to_user"], state_data["amount"]
            from_user = message.from_user.username
            ledger.record_transaction(from_user, to_user, amount, "transfer")
            await message.answer(f"Successfully transferred {amount} to {to_user}!")
        else:
            await message.answer('abort')
        return await state.clear()

    @router.message(Command("daily_prize"))
    async def daily_prize_cmd(message: types.Message, gambler: Gambler):
        if database.is_available_daily_prize(message.from_user.username):
            return await gambler.daily_prize(message)
        else:
            return await message.answer('Your daily prize already obtained! Wait for the next day!')

    @router.message(Command("ledger"))
    async def ledger_cmd(message: types.Message, command: CommandObject):
        txs_count = database.get_transactions_count()

        args = get_args(command, 0, 2)
        limit = int(args[0]) if len(args) >= 1 else 50
        offset = txs_count - int(args[1]) if len(args) == 2 else None

        txs = database.get_transactions(limit=limit, offset=offset)
        return await large_respond(message, [f"<b>Ledger ({txs_count} transactions):</b>"] + txs, parse_mode='html')

    @router.message(Command("leaderboard"))
    async def leaderboard_cmd(message: types.Message, command: CommandObject, ledger: Ledger):
        args = get_args(command, 0, 1)
        is_all = len(args) == 1 and args[0] == "all"
        balances = ledger.get_all_balances() if is_all else ledger.get_all_balances()[1:]

        lines = chain(
            (f"<b>Leaderboard:</b>",),
            (f'{idx if is_all else idx + 1}. {username}: {amount}' for idx, (username, amount) in enumerate(balances))
        )
        return await large_respond(message, lines, parse_mode='html')

    @router.message(Command("export_transactions"))
    async def export_transactions_cmd(message: types.Message, ledger: Ledger):
        file = BufferedInputFile(ledger.export_transactions_csv().encode("utf-8"), filename="transactions.csv")
        return await message.answer_document(file)

    @router.message(Command("blocks"))
    async def blocks_cmd(message: types.Message, command: CommandObject):
        blocks_count = database.get_blocks_count()

        args = get_args(command, 0, 2)
        limit = int(args[0]) if len(args) >= 1 else 50
        offset = blocks_count - int(args[1]) if len(args) == 2 else None

        blocks = database.get_blocks(limit=limit, offset=offset)
        return await large_respond(message, [f"<b>Blocks list ({blocks_count}):</b>"] + blocks, parse_mode='html')

    @router.message(Command("mine_block"))
    async def mine_block_cmd(message: types.Message, ledger: Ledger):
        block = ledger.mine_block()
        if block is None:
            return await message.answer("No pending transactions!")

        return await message.answer(f"Block {block.height} successfully mined by {block.miner}!")

    @router.message(Command("mine"))
    async def mine(message: types.Message, command: CommandObject, ledger: Ledger, user: User):
        args = get_args(command, 0, 1)
        if len(args) == 1 and args[0].isdigit():
            nonce = int(args[0])
        elif len(args) == 1 and args[0] == "random":
            nonce = random.randint(1, 10000)
        else:
            nonce = user.nonce

        user.nonce = nonce
        username = message.from_user.username
        if seconds := database.is_unavailable_mine_attempt(username):
            return await message.answer(f"You already used your mine attempt. Next attempt in {seconds} seconds.")

        hashes = []
        failure_msg = None
        for i in range(storage.mine_block_user_attempts):
            try:
                block = ledger.mine_block(username, nonce)
                await message.answer_animation(
                    "https://media1.tenor.com/m/9qZhM0uswAYAAAAd/bully-maguire-dance.gif",
                    caption=f"<b>SUCCESS! BLOCK REWARD: {storage.mine_block_reward}!</b>\nBlock <b>{block.height}</b> with nonce <b>{block.nonce}</b> mined by <b>{block.miner}</b>!\nBlock hash: <b>{block.block_hash[:16]}...</b>.",
                    parse_mode='html'
                )
                break
            except BlockNotMined as e:
                hashes.append(f"{len(hashes) + 1}. {e.block_hash[:16]}...")
        else:
            hashes = hashes[:8] + hashes[-8:]
            hashes_text = '\n'.join(hashes)
            failure_msg = await message.answer(
                f"<b>FAILURE!</b>\n{storage.mine_block_user_attempts} attempts:\n{hashes_text}\nNext attempt in {storage.mine_block_user_timeout} seconds!",
                parse_mode='html'
            )

        await asyncio.sleep(3)
        if await is_bot_admin(message):
            await message.delete()
        if failure_msg:
            await failure_msg.delete()

        return None

    @router.message(Command("explore_block"))
    async def explore_block_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 1, 1)
        if not args[0].isdigit():
            return await message.answer("Invalid type of arguments!")

        block = database.get_block(int(args[0]))
        if block is None:
            return await message.answer("Block not found!")

        txs = database.get_block_transactions(block, limit=50, ascending=False)
        lines = [
            f"<b>Block {block.height}</b>",
            f"Timestamp: {block.timestamp}",
            f"Miner: {block.miner}",
            f"Nonce: {block.nonce}",
            f"Merkle root: {block.merkle_root}",
            f"Previous hash: {block.prev_hash}",
            f"Hash: {block.block_hash}",
            f"Transactions: {len(txs)}"
        ]
        return await large_respond(message, lines + txs, parse_mode='html')

    @router.message(Command("user_stats"))
    async def user_stats_cmd(message: types.Message, command: CommandObject, ledger: Ledger):
        args = get_args(command, 0, 1)

        if message.reply_to_message:
            username = message.reply_to_message.from_user.username
        elif len(args) == 1:
            username = args[0]
        else:
            username = message.from_user.username

        stats = database.get_user_stats(username)
        if stats is None:
            if username != ledger.genesis_username:
                return await message.answer(f"No statistic for {username} found!")
            stats = database.Stats()

        blackjack_winrate = f"{stats.blackjack_win / stats.blackjack_all:.1%}" if stats.blackjack_all != 0 else "undefined"
        balance = ledger.get_user_balance(username)
        total_gain = ledger.get_user_total_gain(username)

        lines = [
            f"<b>{username} stats:</b>",
            f"Daily prizes opened: {stats.prizes}",
            f"Gamble attempts: {stats.gamble}",
            f"Galton attempts: {stats.galton}",
            f"Mine attempts: {stats.mine}",
            f"Blackjack games played: {stats.blackjack_all}",
            f"Blackjack wins: {stats.blackjack_win}",
            f"Blackjack win rate: {blackjack_winrate}",
            f"Blocks mined: {database.get_user_blocks_count(username)}",
            f"Daily reward amount: {database.get_daily_amount_for_user(username)}",
            f"Balance: {balance}",
            f"Total gain: {total_gain}",
            f"Total loss: {total_gain - balance}",
            f"Max balance recorded: {ledger.get_user_max_balance(username)}"
        ]

        return await large_respond(message, lines, parse_mode='html')

    @router.message(Command("global_stats"))
    async def global_stats_cmd(message: types.Message, ledger: Ledger):
        totals = database.get_total_stats()
        max_balance = ledger.get_all_max_balances()[1]
        total_balance = sum(balance for _, balance in ledger.get_all_balances())
        total_gain = sum(gain for _, gain in ledger.get_all_total_gains())

        blackjack_winrate = f"{totals["blackjack_win"] / totals["blackjack_all"]:.1%}" \
            if totals["blackjack_all"] != 0 else "undefined"

        lines = [
            f"<b>Global stats:</b>",
            f"Daily prizes opened: {totals["prizes"]}",
            f"Gamble attempts: {totals["gamble"]}",
            f"Galton attempts: {totals["galton"]}",
            f"Mine attempts: {totals["mine"]}",
            f"Blackjack games played: {totals["blackjack_all"]}",
            f"Blackjack wins: {totals["blackjack_win"]}",
            f"Blackjack win rate: {blackjack_winrate}",
            f"Blocks mined: {database.get_total_users_blocks_count(ledger.genesis_username)}",
            f"Daily reward amount: {database.get_total_daily_amount()}",
            f"Total balance: {total_balance}",
            f"Total gain: {total_gain}",
            f"Total loss: {total_gain - total_balance}",
            f"Max balance recorded ({max_balance[0]}): {max_balance[1]}"
        ]

        return await large_respond(message, lines, parse_mode='html')

    @router.message(Command("galton_background"))
    async def galton_background_cmd(message: types.Message, state: FSMContext):
        if not message.reply_to_message or message.reply_to_message.photo is None:
            return await message.answer("You need to reply to a message with image!")

        photo = message.reply_to_message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        username = message.from_user.username
        filename = galton_backgrounds_folder_path / f"{username}-temp.png"
        await message.bot.download_file(file.file_path, filename)

        background_filename = PhysicsSimulation().get_test_background(filename)
        background_file = FSInputFile(str(background_filename), filename=filename.name)
        await message.answer_photo(
            background_file, caption=f"Do you want to install this background image for 1000 (y/n)?"
        )
        background_filename.unlink()
        await state.set_data({"filename": filename})
        return await state.set_state(ConfirmationState.galton_background_confirmation)

    @router.message(ConfirmationState.galton_background_confirmation)
    async def galton_background(message: types.Message, state: FSMContext, ledger: Ledger):
        if message.text.lower() == "y":
            tmp_filename: Path = (await state.get_data()).get("filename")
            from_user = message.from_user.username
            ledger.record_deposit(from_user, 1000, "Background galton")

            filename = tmp_filename.parent / f"{from_user}.png"
            tmp_filename.rename(filename)

            database.set_galton_background_path(from_user, str(filename))
            await message.answer(f"Successfully set galton background!")
        else:
            await message.answer('abort')
        await state.clear()

    return router
