import asyncio
from aiogram import types
from lib import database
from lib.gambling.base import BaseGame
from lib.gambling.physics_simulation import PhysicsSimulation
from lib.ledger.ledger import Ledger
from lib.models import MONEY_TYPE, StatsType
from lib.storage import storage
from lib.temporal_storage import UserProfile
from lib.workers import workers


class GaltonGame(BaseGame):
    MIN_BET = 100

    def __init__(self, ledger: Ledger, user: UserProfile, user_bet: MONEY_TYPE = None, user_balls: str | int = None):
        super().__init__(ledger, user, user_bet if user_bet else user.galton_bet)
        self.user_balls = self.user.galton_balls if user_balls is None else int(user_balls)

    async def gamble(self, message: types.Message):
        if self.user.galton_running_count >= storage.galton_max_concurrent_per_user:
            return await message.reply(
                f"The limit of concurrent galtons exceeded! Only {storage.galton_max_concurrent_per_user} concurrent galtons allowed."
            )

        if self.user_balls < 1 or self.user_balls > 750:
            return await message.reply("Amount of balls should be between 1 and 750!")

        if self.user_bet / self.user_balls < 100:
            return await message.reply("Bet per ball should be >= 100!")

        galton_msg = await message.reply(f"Waiting for simulation results /galton {self.gamble_bet} {self.user_balls}")

        self.user.galton_bet = self.user_bet
        self.user.galton_balls = self.user_balls
        self.user.galton_running_count += 1
        database.update_user_stats(self.user.id, StatsType.galton)

        physics_simulation = PhysicsSimulation()
        background_path = database.get_galton_background_path(self.user.id)
        multiplier, filename, duration = await workers.enqueue(physics_simulation.run, self.user_balls, background_path)

        animation = types.FSInputFile(filename, filename=str(filename))
        media = types.InputMediaAnimation(media=animation, caption=None)
        await galton_msg.edit_media(media)
        await asyncio.sleep(duration + 2)

        self.user.galton_running_count -= 1
        multiplier = round(multiplier / self.user_balls, 2)
        self.finish_game("Galton", multiplier)

        return await galton_msg.edit_caption(
            caption=f"Multiplier <b>X{multiplier}</b>! {self.get_balance_str()}", parse_mode="HTML"
        )
