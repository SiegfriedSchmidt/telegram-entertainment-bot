import asyncio
import numpy as np
from aiogram import types
from lib import database
from lib.gambling.games.BaseSlotGame import BaseSlotGame
from lib.ledger.ledger import Ledger
from lib.models import SlotResultType, StatsType, MONEY_TYPE
from lib.temporal_storage import UserProfile

slot_multipliers = {
    SlotResultType.loss: 0,
    SlotResultType.nice_win: 1.2,
    SlotResultType.jackpot: 3,
    SlotResultType.big_jackpot: 11
}


class SlotGame(BaseSlotGame):
    MIN_BET = 20

    def __init__(self, ledger: Ledger, user: UserProfile, user_bet: MONEY_TYPE = None):
        super().__init__(ledger, user, user_bet if user_bet else user.slot_bet)

    async def gamble(self, message: types.Message):
        self.user.slot_bet = self.user_bet

        dice_msg = await self.get_dice_msg(message)
        slot_result = self.determine_slot_result_type(dice_msg.dice.value)
        multiplier = slot_multipliers[slot_result]

        database.update_user_stats(self.user.id, StatsType.slot)
        self.finish_game("Slot", multiplier)
        await asyncio.sleep(1.5)
        return await self.show_win_message(dice_msg, slot_result, multiplier)


if __name__ == '__main__':
    values = np.array(list(slot_multipliers.values()))
    probabilities = np.array([4 * 3 * 2, 3 * 4 * 3, 3, 1]) / 64
    E = np.sum(values * probabilities)
    print(E)
