import asyncio
import numpy as np
from decimal import Decimal
from aiogram import types
from aiogram.types import FSInputFile
from lib.ledger import Ledger
from lib import database
from lib.models import GainType, StatsType
from lib.physics_simulation import PhysicsSimulation
from lib.utils.utils import run_in_thread

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

    async def process_bet(self, message: types.Message, bet: Decimal | str | float = 0) -> float | None:
        username = message.from_user.username
        bet = Decimal(bet)

        if bet < 0:
            await message.reply(f"Bet cannot be negative!")
            return None

        if bet == 0:
            bet = database.get_user_bet(username)
        else:
            database.set_user_bet(username, bet)

        balance = self.ledger.get_user_balance(username)
        if balance < bet:
            await message.reply(f"You don't have enough money: {balance} < {bet}!")
            return None

        return float(bet)

    def get_balance_str(self, username: str) -> str:
        return f'{username}: {self.ledger.get_user_balance(username)} coins.'

    async def gamble(self, message: types.Message, bet: Decimal | str | float = 0):
        bet = await self.process_bet(message, bet)
        if bet is None:
            return None

        if bet < 20:
            return await message.reply("Bet should be greater than 20!")

        username = message.from_user.username
        dice_msg = await self.get_dice_msg(message)

        gain_type = self.determine_gain_type(dice_msg.dice.value)
        gain = int(gamble_multipliers[gain_type] * bet)

        database.update_user_stats(username, StatsType.gamble)
        self.ledger.record_deposit(username, bet, "bet")
        if gain:
            self.ledger.record_gain(username, gain, f"Gamble {gain_type.value}")

        await asyncio.sleep(1.5)
        return await self.show_win_message(dice_msg, gain_type, self.get_balance_str(username))

    async def galton(self, message: types.Message, bet: Decimal | str | float = 0, balls: int = 1):
        bet = await self.process_bet(message, bet)
        if bet is None:
            return None

        if balls < 1 or balls > 100:
            return await message.reply("Amount of balls should be between 1 and 100!")

        bet_per_ball = float(bet / balls)
        if bet_per_ball < 100:
            return await message.reply("Bet per ball should be greater than 100!")

        username = message.from_user.username
        wait_msg = await message.reply("Waiting for simulation results...")

        physics_simulation = PhysicsSimulation()
        multiplier, filename, duration = await run_in_thread(physics_simulation.run, balls)
        gain = int(multiplier * bet_per_ball)
        multiplier = round(multiplier / balls, 2)

        database.update_user_stats(username, StatsType.galton)
        self.ledger.record_deposit(username, bet, "bet")
        if gain:
            self.ledger.record_gain(username, gain, f"Galton X{multiplier}")

        await wait_msg.delete()
        animation = FSInputFile(filename, filename=str(filename))
        galton_msg = await message.reply_animation(animation)

        await asyncio.sleep(duration + 2)
        return await galton_msg.reply(f"Multiplier X{multiplier}! {self.get_balance_str(username)}")

    async def daily_prize(self, message: types.Message):
        username = message.from_user.username
        dice_msg = await self.get_dice_msg(message)
        gain_type = self.determine_gain_type(dice_msg.dice.value)
        gain = daily_multipliers[gain_type]
        self.ledger.record_gain(username, gain, f"Daily {gain_type.value}")

        await asyncio.sleep(1.5)
        return await self.show_win_message(dice_msg, gain_type, self.get_balance_str(username))


if __name__ == '__main__':
    values = np.array(list(gamble_multipliers.values()))
    probabilities = np.array([4 * 3 * 2, 3 * 4 * 3, 3, 1]) / 64
    E = np.sum(values * probabilities)
    print(E)
