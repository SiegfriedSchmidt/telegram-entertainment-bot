import asyncio
import random
from pathlib import Path
from aiogram import Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, FSInputFile, InputMediaAnimation
from aiogram.utils.chat_action import ChatActionMiddleware
from lib import database
from lib.gambling.games.DailySlotGame import DailySlotGame
from lib.gambling.games.SlotGame import SlotGame
from lib.gambling.games.GaltonGame import GaltonGame
from lib.gambling.games.BlackjackGame import BlackjackGame
from lib.bot_commands import text_bot_general_commands, text_bot_admin_commands
from lib.config_reader import config
from lib.init import galton_backgrounds_folder_path
from lib.keyboards.blackjack_keyboard import get_blackjack_keyboard
from lib.ledger.ledger import Ledger
from lib.ledger.chain_manager import BlockNotMined
from lib.api.joke_api import get_joke
from lib.api.meme_api import get_meme
from lib.api.geoip_api import geoip
from lib.llms.general_llm import Dialog
from lib.llms.openrouter import OpenrouterLLM
from lib.middlewares.user_middleware import UserMiddleware
from lib.gambling.physics_simulation import PhysicsSimulation
from lib.gambling.roulette import render_roulette
from lib.states.blackjack_state import BlackjackState
from lib.states.confirmation_state import ConfirmationState
from lib.storage import storage
from lib.temporal_storage import UserProfile
from lib.message_factories.get_leaderboard import get_leaderboard
from lib.utils.general_utils import from_iso
from lib.utils.message_utils import get_args, is_bot_admin, get_name_or_id_with_reply, large_respond
from lib.workers import workers


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
    async def ask_cmd(message: types.Message, command: CommandObject, openrouter_llm: OpenrouterLLM):
        args = command.args
        if args:
            question = args
        else:
            if message.reply_to_message:
                question = message.reply_to_message.text
            else:
                return await message.answer("No question to answer.")

        answer = await message.reply(f'asking {openrouter_llm.model}...')
        dialog = Dialog()
        dialog.add_user_message(question)

        try:
            response = await openrouter_llm.chat_complete(dialog)
        finally:
            await answer.delete()

        return await large_respond(message, response)

    @router.message(Command("change_llm_model"))
    async def change_llm_model_cmd(message: types.Message, command: CommandObject, state: FSMContext,
                                   openrouter_llm: OpenrouterLLM):
        args = get_args(command, 1, 1)
        model = args[0]
        await state.set_state(ConfirmationState.change_llm_model_confirmation)
        await state.set_data({"model": model})
        await message.answer(f'Do you want to change llm model: "{openrouter_llm.model}" -> "{model}"? (y/n)')

    @router.message(ConfirmationState.change_llm_model_confirmation)
    async def change_llm_model(message: types.Message, state: FSMContext, openrouter_llm: OpenrouterLLM):
        if message.text.lower() == "y":
            state_data = await state.get_data()
            model = state_data["model"]
            openrouter_llm.model = model
            await message.answer(f"Changed llm model to {model}!")
        else:
            await message.answer('abort')
        return await state.clear()

    @router.message(Command("change_llm_key"))
    async def change_llm_key_cmd(message: types.Message, command: CommandObject, state: FSMContext,
                                 openrouter_llm: OpenrouterLLM):
        args = get_args(command, 1, 1)
        api_key = args[0]
        await state.set_state(ConfirmationState.change_llm_key_confirmation)
        await state.set_data({"api_key": api_key})
        await message.answer(
            f'Do you want to change llm api key: "{openrouter_llm.api_key[:16]}" -> "{api_key[:16]}"? (y/n)'
        )

    @router.message(ConfirmationState.change_llm_key_confirmation)
    async def change_llm_key(message: types.Message, state: FSMContext, openrouter_llm: OpenrouterLLM):
        if message.text.lower() == "y":
            state_data = await state.get_data()
            api_key = state_data["api_key"]
            openrouter_llm.api_key = api_key
            await message.answer(f"Changed llm api key to {api_key[:16]}!")
        else:
            await message.answer('abort')
        return await state.clear()

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
    async def gamble_cmd(message: types.Message, command: CommandObject, ledger: Ledger, user: UserProfile):
        args = get_args(command, 0, 1)
        bet = args[0] if len(args) == 1 else None
        return await SlotGame(ledger, user, bet).gamble(message)

    @router.message(Command("galton"))
    async def galton_cmd(message: types.Message, command: CommandObject, ledger: Ledger, user: UserProfile):
        args = get_args(command, 0, 2)
        bet = args[0] if len(args) >= 1 else None
        balls = args[1] if len(args) == 2 else ('1' if len(args) == 1 else None)
        return await GaltonGame(ledger, user, bet, balls).gamble(message)

    @router.message(Command("blackjack"))
    async def blackjack_cmd(message: types.Message, command: CommandObject, state: FSMContext, user: UserProfile,
                            ledger: Ledger):
        args = get_args(command, 0, 1)
        bet = args[0] if len(args) == 1 else user.blackjack_bet

        blackjack = BlackjackGame(ledger, user, bet)
        filename = blackjack.start()
        image = FSInputFile(filename, filename=str(filename))
        user.blackjack_bet = bet

        game_message = await message.reply_photo(
            image,
            caption=f"Blackjack, bet: <b>{bet}</b>.",
            reply_markup=get_blackjack_keyboard(user.id),
            parse_mode="HTML"
        )

        await state.set_state(BlackjackState.blackjack_activated)
        return await state.set_data({"blackjack": blackjack, "game_message": game_message})

    @router.message(Command("roulette"))
    async def roulette_cmd(message: types.Message):
        roulette_msg = await message.reply("Start roulette...")
        filename, duration, win_number = await workers.enqueue(render_roulette)

        animation = FSInputFile(filename, filename=str(filename))
        media = InputMediaAnimation(media=animation, caption=None)
        await roulette_msg.edit_media(media)

        await asyncio.sleep(duration)
        await roulette_msg.edit_caption(caption=f"Win number: {win_number}!")

    @router.message(Command("balance"))
    async def balance_cmd(message: types.Message, ledger: Ledger, user: UserProfile):
        return await message.answer(f"Your balance is {ledger.get_user_balance(user.id)}.")

    @router.message(Command("transfer"))
    async def transfer_cmd(message: types.Message, command: CommandObject, state: FSMContext, ledger: Ledger,
                           user: UserProfile):
        args = get_args(command, 0, 2)
        if message.reply_to_message:
            to_user_raw = message.reply_to_message.from_user.id
            if len(args) == 1 and args[0].isdecimal():
                amount = args[0]
            else:
                return await message.answer('Correct amount is required!')
        elif len(args) == 2 and args[0].isdecimal():
            amount = args[0]
            to_user_raw = args[1]
        elif len(args) == 2 and args[1].isdecimal():
            amount = args[1]
            to_user_raw = args[0]
        else:
            return await message.answer('Invalid syntax!')

        to_user = database.get_user(to_user_raw)

        if to_user is None:
            return await message.answer(f'User {to_user_raw} does not exists!')

        if user.id == to_user.id:
            return await message.answer("You can't transfer to yourself!")

        me = await message.bot.me()
        if to_user.id == me.id:
            await state.set_state(ConfirmationState.transfer_confirmation)
            await state.set_data({"to_user": to_user, "amount": amount})
            return await message.answer(
                f"Are you sure you want to transfer {amount} to me 👉👈 (y/n)?"
            )

        ledger.record_transaction(user.id, to_user.id, amount, "transfer")
        return await message.answer(f"Successfully transferred {amount} to {to_user}!")

    @router.message(ConfirmationState.transfer_confirmation)
    async def transfer(message: types.Message, state: FSMContext, ledger: Ledger, user: UserProfile):
        state_data = await state.get_data()
        await state.clear()
        if message.text.lower() == "y":
            to_user, amount = state_data["to_user"], state_data["amount"]
            ledger.record_transaction(user.id, to_user.id, amount, "transfer")
            await message.answer(f"Successfully transferred {amount} to {to_user}!")
        else:
            await message.answer('abort')

    @router.message(Command("daily_prize"))
    async def daily_prize_cmd(message: types.Message, ledger: Ledger, user: UserProfile):
        if database.is_available_daily_prize(user.id):
            return await DailySlotGame(ledger, user).gamble(message)
        else:
            return await message.answer('Your daily prize already obtained! Wait for the next day!')

    @router.message(Command("ledger"))
    async def ledger_cmd(message: types.Message, command: CommandObject):
        txs_count = database.get_transactions_count()

        args = get_args(command, 0, 3)
        biggest = False
        if len(args) >= 1 and not args[0].isdigit():
            if args[0] != "biggest":
                return await message.answer(f'Invalid option "{args[0]}"!')
            biggest = True
            args.pop(0)

        limit = int(args[0]) if len(args) >= 1 else 20
        offset = txs_count - int(args[1]) if len(args) == 2 else None

        if biggest:
            if offset is None:
                offset = 1

        txs = database.get_transactions(limit=limit, offset=offset, biggest=biggest)
        return await large_respond(message, [f"<b>Ledger ({txs_count} transactions):</b>"] + txs, parse_mode='html')

    @router.message(Command("leaderboard"))
    async def leaderboard_cmd(message: types.Message, command: CommandObject, ledger: Ledger):
        args = get_args(command, 0, 1)
        is_all = len(args) == 1 and args[0] == "all"
        lines = get_leaderboard(ledger, is_all)
        return await large_respond(message, lines, parse_mode='html')

    @router.message(Command("export_transactions"))
    async def export_transactions_cmd(message: types.Message, ledger: Ledger):
        file = BufferedInputFile(ledger.export_transactions_csv().encode("utf-8"), filename="transactions.csv")
        return await message.answer_document(file)

    @router.message(Command("blocks"))
    async def blocks_cmd(message: types.Message, command: CommandObject):
        blocks_count = database.get_blocks_count()

        args = get_args(command, 0, 2)
        limit = int(args[0]) if len(args) >= 1 else 10
        offset = blocks_count - int(args[1]) if len(args) == 2 else None

        blocks = database.get_blocks(limit=limit, offset=offset)
        return await large_respond(message, [f"<b>Blocks list ({blocks_count}):</b>"] + blocks, parse_mode='html')

    @router.message(Command("total_pending_fees"))
    async def total_pending_fees_cmd(message: types.Message):
        return await message.reply(f"Total pending fees: {database.get_total_pending_fees()}")

    @router.message(Command("user_blocks"))
    async def user_blocks_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 0, 3)
        if len(args) >= 1:
            user_raw = args[0]
            args.pop(0)
        else:
            user_raw = await get_name_or_id_with_reply(message)

        user = database.get_user(user_raw)
        if user is None:
            return await message.answer(f"User {user} does not exist!")

        blocks_count = database.get_user_blocks_count(user.id)
        limit = int(args[0]) if len(args) >= 1 else 10
        offset = blocks_count - int(args[1]) if len(args) == 2 else None

        blocks = database.get_user_blocks(user.id, limit=limit, offset=offset)
        return await large_respond(
            message, [f"<b>Blocks {user} list ({blocks_count}):</b>"] + blocks, parse_mode='html'
        )

    @router.message(Command("mine_block"))
    async def mine_block_cmd(message: types.Message, ledger: Ledger):
        block = ledger.mine_block()
        if block is None:
            return await message.answer("No pending transactions!")

        return await message.answer(f"Block {block.height} successfully mined by {block.miner}!")

    @router.message(Command("mine"))
    async def mine(message: types.Message, command: CommandObject, ledger: Ledger, user: UserProfile):
        args = get_args(command, 0, 1)
        if len(args) == 1 and args[0].isdigit():
            nonce = int(args[0])
        elif len(args) == 1 and args[0] == "random":
            nonce = random.randint(1, 10000)
        else:
            nonce = user.nonce

        user.nonce = nonce
        if seconds := database.is_unavailable_mine_attempt(user.id):
            return await message.answer(f"You already used your mine attempt. Next attempt in {seconds} seconds.")

        hashes = []
        failure_msg = None
        for i in range(storage.mine_block_user_attempts):
            try:
                block = ledger.mine_block(user.id, nonce)
                await message.answer_animation(
                    "https://media1.tenor.com/m/9qZhM0uswAYAAAAd/bully-maguire-dance.gif",
                    caption=f"<b>SUCCESS! BLOCK REWARD: {block.base_reward + block.total_fees} (fees {block.total_fees})!"
                            f"</b>\nBlock <b>{block.height}</b> with nonce <b>{block.nonce}</b> mined by <b>{block.miner}</b>!\n"
                            f"Block hash: <b>{block.block_hash[:16]}...</b>.",
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
            f"Timestamp: {from_iso(block.timestamp)}",
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
        user_raw = await get_name_or_id_with_reply(message, args[0] if len(args) == 1 else None)
        user = database.get_user(user_raw)
        stats = database.get_user_stats(user)
        if stats is None:
            if user.id != ledger.genesis_id:
                return await message.answer(f"No statistic for {user} found!")
            stats = database.Stats()

        blackjack_winrate = f"{stats.blackjack_win / stats.blackjack_all:.1%}" if stats.blackjack_all != 0 else "undefined"
        balance = ledger.get_user_balance(user.id)
        # total_gain = ledger.get_user_total_gain(user.id)

        lines = [
            f"<b>{user} stats:</b>",
            f"Daily prizes opened: {stats.prizes}",
            f"Gamble attempts: {stats.gamble}",
            f"Galton attempts: {stats.galton}",
            f"Mine attempts: {stats.mine}",
            f"Blackjack games played: {stats.blackjack_all}",
            f"Blackjack wins: {stats.blackjack_win}",
            f"Blackjack win rate: {blackjack_winrate}",
            f"Blocks mined: {database.get_user_blocks_count(user.id)}",
            f"Daily reward amount: {database.get_daily_amount_for_user(user.id)}",
            f"Balance: {balance}",
            # f"Total gain: {total_gain}",
            # f"Total loss: {total_gain - balance}",
            f"Max balance recorded: {ledger.get_user_max_balance(user.id)}"
        ]

        return await large_respond(message, lines, parse_mode='html')

    @router.message(Command("global_stats"))
    async def global_stats_cmd(message: types.Message, ledger: Ledger):
        totals = database.get_total_stats()
        max_balance = ledger.get_all_max_balances()[1]
        total_balance = sum(balance for _, balance in ledger.get_all_balances()[1:])
        # total_gain = sum(gain for _, gain in ledger.get_all_total_gains())

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
            f"Blocks mined: {database.get_total_users_blocks_count(ledger.genesis_id)}",
            f"Daily reward amount: {database.get_total_daily_amount()}",
            f"Total balance: {total_balance}",
            # f"Total gain: {total_gain}",
            # f"Total loss: {total_gain - total_balance}",
            f"Max balance recorded ({max_balance[0]}): {max_balance[1]}"
        ]

        return await large_respond(message, lines, parse_mode='html')

    @router.message(Command("galton_background"))
    async def galton_background_cmd(message: types.Message, state: FSMContext, user: UserProfile):
        if not message.reply_to_message or message.reply_to_message.photo is None:
            return await message.answer("You need to reply to a message with image!")

        photo = message.reply_to_message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        filename = galton_backgrounds_folder_path / f"{user}-temp.png"
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
    async def galton_background(message: types.Message, state: FSMContext, ledger: Ledger, user: UserProfile):
        if message.text.lower() == "y":
            tmp_filename: Path = (await state.get_data()).get("filename")
            ledger.record_deposit(user.id, 1000, "Background galton")

            filename = tmp_filename.parent / f"{user}.png"
            tmp_filename.rename(filename)

            database.set_galton_background_path(user.id, str(filename))
            await message.answer(f"Successfully set galton background!")
        else:
            await message.answer('abort')
        await state.clear()

    return router
