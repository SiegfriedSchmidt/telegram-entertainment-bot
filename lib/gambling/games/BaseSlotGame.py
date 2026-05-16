from lib.gambling.base import BaseGame
from lib.models import SlotResultType
from aiogram import types


class BaseSlotGame(BaseGame):
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

    async def show_win_message(self, dice_msg: types.Message, slot_result_type: SlotResultType,
                               multiplier: float = None):
        message_end = (f"X{multiplier} " if multiplier else " ") + self.get_balance_str()
        match slot_result_type.value:
            case SlotResultType.big_jackpot:
                await dice_msg.reply_animation(
                    'https://media1.tenor.com/m/Rpk3q-OLFeYAAAAd/hakari-dance-hakari.gif',
                    caption=f"🎉 **BIG JACKPOT!** 🎉! {message_end}"
                )
            case SlotResultType.jackpot:
                await dice_msg.reply(f"🎉 **JACKPOT!** 🎉! {message_end}")
            case SlotResultType.nice_win:
                await dice_msg.reply(f"✨ Nice win! ✨! {message_end}")
            case SlotResultType.loss:
                await dice_msg.reply(f"😢 Better luck next time 😢! {message_end}")

    def determine_slot_result_type(self, dice_val: int) -> SlotResultType:
        result = self.convert_dice_val(dice_val)
        unique = len(set(result))
        if result == '333':
            return SlotResultType.big_jackpot
        elif unique == 1:
            return SlotResultType.jackpot
        elif unique == 2:
            return SlotResultType.nice_win
        else:
            return SlotResultType.loss
