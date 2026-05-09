import asyncio
import numpy as np
from aiogram import types
from aiogram.types import FSInputFile, InputMediaAnimation
from lib.ledger import Ledger
from lib import database
from lib.models import GainType, StatsType
from lib.physics_simulation import PhysicsSimulation
from lib.storage import storage
from lib.temporal_storage import UserProfile
from lib.utils.general_utils import run_in_thread

gamble_multipliers = {
    GainType.loss: 0,
    GainType.nice_win: 1.2,
    GainType.jackpot: 3,
    GainType.big_jackpot: 11
}

daily_multipliers = {
    GainType.loss: 500,
    GainType.nice_win: 1200,
    GainType.jackpot: 3000,
    GainType.big_jackpot: 10000
}


class Gambler:
    def __init__(self, ledger: Ledger):
        self.ledger = ledger

    @staticmethod
    def convert_dice_val(dice_val: int):
        # bar, plum, lemon, seven
        val = dice_val - 1

        result = ''
        while val > 0:
            result += str(val % 4)
            val //= 4
        return result.ljust(3, '0')

    @staticmethod
    async def get_dice_msg(message: types.Message):
        try:
            if message.dice.value:
                dice_msg = message
            else:
                raise AttributeError
        except AttributeError:
            dice_msg = await message.reply_dice(emoji="🎰")

        return dice_msg

    @staticmethod
    async def show_win_message(dice_msg: types.Message, gain_type: GainType, balance_str: str):
        match gain_type.value:
            case GainType.big_jackpot:
                await dice_msg.reply_animation(
                    'https://media1.tenor.com/m/Rpk3q-OLFeYAAAAd/hakari-dance-hakari.gif',
                    caption=f"🎉 **BIG JACKPOT!** X{gamble_multipliers[gain_type]}! 🎉 {balance_str}"
                )
            case GainType.jackpot:
                await dice_msg.reply(f"🎉 **JACKPOT!** X{gamble_multipliers[gain_type]}! 🎉 {balance_str}")
            case GainType.nice_win:
                await dice_msg.reply(f"✨ Nice win! X{gamble_multipliers[gain_type]}! ✨ {balance_str}")
            case GainType.loss:
                await dice_msg.reply(f"😢 Better luck next time, loser! {balance_str}")

    def determine_gain_type(self, dice_val: int) -> GainType:
        result = self.convert_dice_val(dice_val)
        unique = len(set(result))
        if result == '333':
            return GainType.big_jackpot
        elif unique == 1:
            return GainType.jackpot
        elif unique == 2:
            return GainType.nice_win
        else:
            return GainType.loss

    @staticmethod
    async def validate_bet(user_bet: str | int) -> int:
        if isinstance(user_bet, int):
            bet = user_bet
        elif user_bet.isdigit():
            bet = int(user_bet)
        else:
            raise RuntimeError("Bet should be a digit!")

        if bet < 0:
            raise RuntimeError("Bet cannot be negative!")

        return int(bet)

    def get_balance_str(self, user: UserProfile) -> str:
        return f'{user}: {self.ledger.get_user_balance(user.id)} coins.'

    async def gamble(self, message: types.Message, user: UserProfile, user_bet: str = None):
        bet = await self.validate_bet(user.gamble_bet if user_bet is None else user_bet)

        if bet < 20:
            return await message.reply("Bet should be greater than 20!")

        self.ledger.record_deposit(user.id, bet, "Gamble bet")
        user.gamble_bet = bet

        dice_msg = await self.get_dice_msg(message)
        gain_type = self.determine_gain_type(dice_msg.dice.value)
        gain = int(gamble_multipliers[gain_type] * bet)

        database.update_user_stats(user.id, StatsType.gamble)
        if gain:
            self.ledger.record_gain(user.id, gain, f"Gamble gain X{gamble_multipliers[gain_type]}")

        await asyncio.sleep(1.5)
        return await self.show_win_message(dice_msg, gain_type, self.get_balance_str(user))

    async def galton(self, message: types.Message, user: UserProfile, user_bet: str = None, user_balls: str = None):
        bet = await self.validate_bet(user.galton_bet if user_bet is None else user_bet)
        balls = user.galton_balls if user_balls is None else int(user_balls)

        if user.galton_running_count >= storage.galton_max_concurrent_per_user:
            return await message.reply(
                f"The limit of concurrent galtons exceeded! Only {storage.galton_max_concurrent_per_user} concurrent galtons allowed."
            )

        if balls < 1 or balls > 750:
            return await message.reply("Amount of balls should be between 1 and 750!")

        bet_per_ball = float(bet / balls)
        if bet_per_ball < 100:
            return await message.reply("Bet per ball should be >= 100!")

        self.ledger.record_deposit(user.id, bet, "Galton bet")
        galton_msg = await message.reply(f"Waiting for simulation results /galton {bet} {balls}")

        user.galton_bet = bet
        user.galton_balls = balls
        user.galton_running_count += 1
        database.update_user_stats(user.id, StatsType.galton)

        physics_simulation = PhysicsSimulation()
        background_path = database.get_galton_background_path(user.id)
        multiplier, filename, duration = await run_in_thread(physics_simulation.run, balls, background_path)

        animation = FSInputFile(filename, filename=str(filename))
        media = InputMediaAnimation(media=animation, caption=None)
        await galton_msg.edit_media(media)
        await asyncio.sleep(duration + 2)

        user.galton_running_count -= 1
        gain = int(multiplier * bet_per_ball)
        multiplier = round(multiplier / balls, 2)
        if gain:
            self.ledger.record_gain(user.id, gain, f"Galton gain X{multiplier}")

        return await galton_msg.edit_caption(
            caption=f"Multiplier <b>X{multiplier}</b>! {self.get_balance_str(user)}", parse_mode="HTML"
        )

    async def daily_prize(self, message: types.Message, user: UserProfile):
        dice_msg = await self.get_dice_msg(message)
        gain_type = self.determine_gain_type(dice_msg.dice.value)
        gain = daily_multipliers[gain_type]
        self.ledger.record_gain(user.id, gain, f"Daily {gain_type.value}")

        await asyncio.sleep(1.5)
        return await self.show_win_message(dice_msg, gain_type, self.get_balance_str(user))


if __name__ == '__main__':
    values = np.array(list(gamble_multipliers.values()))
    probabilities = np.array([4 * 3 * 2, 3 * 4 * 3, 3, 1]) / 64
    E = np.sum(values * probabilities)
    print(E)
