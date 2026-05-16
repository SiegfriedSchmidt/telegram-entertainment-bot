import asyncio
from aiogram import types
from lib.gambling.games.BaseSlotGame import BaseSlotGame
from lib.ledger.ledger import Ledger
from lib.models import SlotResultType
from lib.temporal_storage import UserProfile

daily_slot_multipliers = {
    SlotResultType.loss: 500,
    SlotResultType.nice_win: 1200,
    SlotResultType.jackpot: 3000,
    SlotResultType.big_jackpot: 10000
}


class DailySlotGame(BaseSlotGame):
    MIN_BET = 20

    def __init__(self, ledger: Ledger, user: UserProfile):
        super().__init__(ledger, user, 0)

    async def gamble(self, message: types.Message):
        dice_msg = await self.get_dice_msg(message)
        slot_result = self.determine_slot_result_type(dice_msg.dice.value)
        win_amount = daily_slot_multipliers[slot_result]
        self.finish_game("Daily slot", raw_win_amount=win_amount)

        await asyncio.sleep(1.5)
        return await self.show_win_message(dice_msg, slot_result)
