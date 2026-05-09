from aiogram import Router, types
from aiogram.filters import Command

router = Router()


@router.message(Command("chat_id"))
async def chat_id_cmd(message: types.Message):
    return await message.reply(str(message.chat.id))


@router.message(Command("user_id"))
async def user_id_cmd(message: types.Message):
    if message.reply_to_message:
        return await message.reply(
            f'{message.reply_to_message.from_user.username}: {message.reply_to_message.from_user.id}'
        )
    return await message.reply(f'{message.from_user.username}: {message.from_user.id}')
