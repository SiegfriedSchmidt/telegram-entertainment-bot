import asyncio
from decimal import Decimal
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile
from aiogram.utils.chat_action import ChatActionMiddleware
from lib import database
from lib.bot_commands import text_bot_general_commands, text_bot_admin_commands
from lib.config_reader import config
from lib.database import get_user_blocks_count, get_total_users_blocks_count
from lib.ledger import Ledger, BlockNotMined
from lib.api.gemini_api import gemini_api
from lib.api.joke_api import get_joke
from lib.api.meme_api import get_meme
from lib.api.geoip_api import geoip
from lib.gambler import Gambler
from lib.middlewares.user_middleware import UserMiddleware
from lib.states.confirmation_state import ConfirmationState
from lib.storage import storage
from lib.temporal_storage import User
from lib.utils.utils import get_args, large_respond


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
        args = get_args(command)
        if len(args) > 1:
            return await message.answer('too many args!')

        try:
            joke_type = args[0] if len(args) == 1 else None
            joke = await get_joke(joke_type)
        except Exception as e:
            return await message.answer(str(e))
        return await message.answer(joke)

    @router.message(Command("meme"))
    async def meme_cmd(message: types.Message, command: CommandObject):
        args = get_args(command)
        if len(args) > 1:
            return await message.answer('too many args!')

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
        args = get_args(command)
        if len(args) == 0:
            return await message.answer('too few args!')

        if len(args) > 1:
            return await message.answer('too many args!')

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
    async def gamble_cmd(message: types.Message, command: CommandObject, gambler: Gambler):
        args = get_args(command)
        bet = 0
        if len(args) == 1:
            if not args[0].isdecimal() or (bet := Decimal(args[0])) < 0:
                return await message.answer('bet should be decimal and be greater than 0!')

        if len(args) > 1:
            return await message.answer('too many args!')

        return await gambler.gamble(message, bet)

    @router.message(Command("galton"))
    async def galton_cmd(message: types.Message, command: CommandObject, gambler: Gambler):
        args = get_args(command)
        bet = 0
        balls = 1
        if len(args) >= 1:
            if not args[0].isdecimal() or (bet := Decimal(args[0])) < 0:
                return await message.answer('bet should be decimal and be greater than 0!')

        if len(args) == 2:
            if not args[1].isdigit() or (balls := int(args[1])) < 1:
                return await message.answer('number of balls should be decimal and be greater than 0!')

        if len(args) > 2:
            return await message.answer('too many args!')

        return await gambler.galton(message, bet, balls)

    @router.message(Command("balance"))
    async def balance_cmd(message: types.Message, ledger: Ledger):
        return await message.answer(f"Your balance is {ledger.get_user_balance(message.from_user.username)}.")

    @router.message(Command("transfer"))
    async def transfer_cmd(message: types.Message, command: CommandObject, state: FSMContext, ledger: Ledger):
        args = get_args(command)
        if message.reply_to_message:
            to_user = message.reply_to_message.from_user.username
            if len(args) == 1 and args[0].isdecimal():
                amount = args[0]
            else:
                return await message.answer('Correct amount is required!')
        elif len(args) == 2 and args[0].isdecimal():
            amount = args[0]
            to_user = args[1]
        else:
            return await message.answer('Invalid syntax!')

        from_user = message.from_user.username
        if from_user == to_user:
            return await message.answer("You can't transfer to yourself!")

        me = await message.bot.me()
        is_user_me = to_user == me.username
        if is_user_me or not database.is_user_exists(to_user):
            await state.set_state(ConfirmationState.transfer_confirmation)
            await state.set_data({"to_user": to_user, "amount": amount})
            return await message.answer(
                f"Are you sure you want to transfer {amount} to {'me' if is_user_me else 'nonexistent user'} (y/n)?"
            )

        ledger.record_transaction(from_user, to_user, amount, "transfer")
        return await message.answer(f"Successfully transferred {amount} to {to_user}!")

    @router.message(ConfirmationState.transfer_confirmation)
    async def transfer(message: types.Message, state: FSMContext, ledger: Ledger):
        if message.text == "y":
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
    async def ledger_cmd(message: types.Message):
        txs = database.get_transactions(limit=50)
        txs_count = database.get_transactions_count()
        text_txs = '\n'.join([
            f'{tx.number}. {tx.from_user} -> {tx.to_user}, {tx.amount}, {tx.description} - {"pending" if tx.block is None else f"block {tx.block.height}"}'
            for tx in txs
        ])
        return await message.answer(f"<b>Ledger ({txs_count} transactions):</b>\n{text_txs}", parse_mode='html')

    @router.message(Command("leaderboard"))
    async def leaderboard_cmd(message: types.Message, command: CommandObject, ledger: Ledger):
        args = get_args(command)
        balances = ledger.get_all_balances() if len(args) == 1 and args[0] == "all" else ledger.get_all_balances()[1:]

        text = '\n'.join([
            f'{idx + 1}. {username}: {amount}' for idx, (username, amount) in enumerate(balances)
        ])
        return await message.answer(f"<b>Leaderboard:</b>\n{text}", parse_mode='html')

    @router.message(Command("export_transactions"))
    async def export_transactions_cmd(message: types.Message, ledger: Ledger):
        file = BufferedInputFile(ledger.export_transactions_csv().encode("utf-8"), filename="transactions.csv")
        return await message.answer_document(file)

    @router.message(Command("blocks"))
    async def blocks_cmd(message: types.Message):
        blocks = database.get_blocks(limit=50)
        blocks_count = database.get_blocks_count()
        text_blocks = '\n'.join(
            [f'Block: {b.height}, miner: {b.miner}, nonce: {b.nonce}, hash: {b.block_hash[:16]}...' for b in blocks]
        )
        return await message.answer(f"<b>Blocks list ({blocks_count}):</b>\n{text_blocks}", parse_mode='html')

    @router.message(Command("mine_block"))
    async def mine_block_cmd(message: types.Message, ledger: Ledger):
        block = ledger.mine_block()
        if block is None:
            return await message.answer("No pending transactions!")

        return await message.answer(f"Block {block.height} successfully mined by {block.miner}!")

    @router.message(Command("mine_block_attempt"))
    async def mine_block_attempt(message: types.Message, command: CommandObject, ledger: Ledger, user: User):
        args = get_args(command)
        if len(args) == 1 and args[0].isdigit():
            nonce = int(args[0])
            user.nonce = nonce
        else:
            nonce = user.nonce

        username = message.from_user.username
        if seconds := database.is_unavailable_mine_attempt(username):
            return await message.answer(f"You already used your mine attempt. Next attempt in {seconds} seconds.")

        hashes = []
        for i in range(storage.mine_block_user_attempts):
            try:
                block = ledger.mine_block(username, nonce)
                return await message.answer_animation(
                    "https://media1.tenor.com/m/9qZhM0uswAYAAAAd/bully-maguire-dance.gif",
                    caption=f"<b>SUCCESS! BLOCK REWARD: {storage.mine_block_reward}!</b>\nBlock <b>{block.height}</b> with nonce <b>{block.nonce}</b> mined by <b>{block.miner}</b>!\nBlock hash: <b>{block.block_hash[:16]}...</b>.",
                    parse_mode='html'
                )
            except BlockNotMined as e:
                hashes.append(e.block_hash[:16] + "...")

        hashes_text = '\n'.join(hashes)
        failure_msg = await message.answer(
            f"<b>FAILURE!</b>\n{hashes_text}\nNext attempt in {storage.mine_block_user_timeout} seconds!",
            parse_mode='html'
        )
        await asyncio.sleep(3)
        return await failure_msg.delete()

    @router.message(Command("explore_block"))
    async def explore_block_cmd(message: types.Message, command: CommandObject):
        args = get_args(command)
        if len(args) != 1 or not args[0].isdigit():
            return await message.answer("Invalid number or type of arguments!")

        block = database.get_block(int(args[0]))
        if block is None:
            return await message.answer("Block not found!")

        txs = database.get_block_transactions(block, limit=50, ascending=False)

        text_block = f"Block {block.height}:\nTimestamp: {block.timestamp}\nMiner: {block.miner}\nNonce: {block.nonce}\nMerkle root: {block.merkle_root}\nPrevious hash: {block.prev_hash}\nHash: {block.block_hash}\nTransactions: {len(txs)}"
        text_txs = '\n'.join([
            f"{tx.number}. {tx.from_user} -> {tx.to_user}, {tx.amount}, {tx.description}" for tx in txs
        ])

        return await message.answer(f"{text_block}\n{text_txs}")

    @router.message(Command("user_stats"))
    async def user_stats_cmd(message: types.Message, command: CommandObject, ledger: Ledger):
        args = get_args(command)

        if message.reply_to_message:
            username = message.reply_to_message.from_user.username
        elif len(args) == 1:
            username = args[0]
        else:
            username = message.from_user.username

        stats = database.get_user_stats(username)
        if stats is None:
            return await message.answer(f"No statistic for {username} found!")

        return await message.answer(
            f"<b>{username} stats:</b>\nDaily prizes opened: {stats.prizes}\nGamble attempts: {stats.gamble}\nGalton attempts: {stats.galton}\nMine attempts: {stats.mine}\nBlocks mined: {get_user_blocks_count(username)}\nDaily reward amount: {database.get_daily_amount_for_user(username)}\nMax balance recorded: {ledger.get_user_max_balance(username)}",
            parse_mode='html'
        )

    @router.message(Command("global_stats"))
    async def global_stats_cmd(message: types.Message, ledger: Ledger):
        totals = database.get_total_stats()
        return await message.answer(
            f"<b>Global stats:</b>\nDaily prizes opened: {totals["prizes"]}\nGamble attempts: {totals["gamble"]}\nGalton attempts: {totals["galton"]}\nMine attempts: {totals["mine"]}\nBlocks mined: {get_total_users_blocks_count(ledger.genesis_username)}\nDaily reward amount: {database.get_total_daily_amount()}",
            parse_mode='html'
        )

    return router
