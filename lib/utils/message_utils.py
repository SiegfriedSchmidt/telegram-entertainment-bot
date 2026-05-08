import asyncio
from pathlib import Path
from typing import List, runtime_checkable, Protocol, Union, Iterable
from aiogram import types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner


def get_args(command: CommandObject, min_args=-1, max_args=-1) -> List[str]:
    args = command.args.split() if command.args else []
    args_count = len(args)
    if min_args != -1 and args_count < min_args:
        raise RuntimeError(f"Too few arguments {args_count} < {min_args}.")
    elif max_args != -1 and args_count > max_args:
        raise RuntimeError(f"Too many arguments {args_count} > {max_args}.")

    return args


async def is_bot_admin(message: types.Message) -> bool:
    try:
        bot = message.bot
        member = await bot.get_chat_member(message.chat.id, bot.id)
        if isinstance(member, (ChatMemberAdministrator, ChatMemberOwner)):
            return True

        return False
    except TelegramAPIError:
        return False


async def save_document(message: types.Message, path: str | Path) -> None:
    doc = message.reply_to_message.document
    file = await message.bot.get_file(doc.file_id)
    downloaded_file = await message.bot.download_file(file.file_path)

    with open(path, "wb") as f:
        f.write(downloaded_file.read())


async def get_name_or_id_with_reply(message: types.Message, arg: str | None = None) -> str | int:
    if message.reply_to_message:
        name_or_id = message.reply_to_message.from_user.id
    elif arg is not None:
        name_or_id = arg
    else:
        name_or_id = message.from_user.id

    return name_or_id


@runtime_checkable
class Stringable(Protocol):
    def __str__(self) -> str: ...


async def large_respond(message: types.Message, printable: Union[str, Iterable[Stringable | str]],
                        timeout=3, characters=3000, maximum=6, **kwargs) -> bool:
    if not printable:
        await message.answer("Nothing.")
        return True
    elif isinstance(printable, str):
        string = printable if isinstance(printable, str) else str(printable)

        if len(string) >= characters * 4:
            await message.answer("Too large.")
            return False
        for i in range(0, len(string), characters):
            await message.answer(string[i:i + characters], **kwargs)
            await asyncio.sleep(timeout)
    elif isinstance(printable, Iterable):
        divided_message = []
        message_part = ''
        cnt = 0
        for obj in printable:
            item = (obj if isinstance(obj, str) else str(obj)) + '\n'

            cnt += len(item)
            if cnt >= characters:
                divided_message.append(message_part.strip())
                message_part = ''
                cnt = len(item)

            message_part += item

        if message_part:
            divided_message.append(message_part)

        if len(divided_message) >= maximum:
            await message.answer("Too large.")
            return False

        for message_part in divided_message:
            await message.answer(message_part, **kwargs)
            await asyncio.sleep(timeout)
    else:
        await message.answer("I've get smth else than a str or Iterable.")

    return True
