import asyncio
import os
import re
from datetime import datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from typing import List, Iterable, Tuple, Protocol, Union, runtime_checkable
from aiogram import types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner


def get_file_from_str(string: str, filename: str) -> BytesIO:
    file = BytesIO(str(string).encode("utf-8"))
    file.name = filename
    return file


def get_dir_size(path: Path | str):
    total = 0
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                total += entry.stat().st_size
            elif entry.is_dir():
                total += get_dir_size(entry.path)
    return total


def clear_dir_contents(path: Path | str) -> List[Tuple[str, int]]:
    files: List[Tuple[str, int]] = []
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                files.append((entry.name, entry.stat().st_size))
                os.remove(entry.path)
            elif entry.is_dir():
                files.extend(clear_dir_contents(entry.path))
    return files


def remove_file(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError()
    filesize = path.stat().st_size
    os.remove(path)
    return filesize


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


def used_today(last_used: datetime, day_start_time: str) -> bool:
    hour, minute = map(int, day_start_time.split(":"))
    start_time = time(hour, minute)

    now = datetime.now()

    # Construct today's start time
    today_start = datetime.combine(now.date(), start_time)

    # Determine actual logical day start
    if now < today_start:
        # Day started yesterday
        day_start = today_start - timedelta(days=1)
    else:
        # Day started today
        day_start = today_start

    day_end = day_start + timedelta(days=1)

    return day_start <= last_used < day_end


def is_valid_mac_address(mac: str) -> bool:
    patterns = [
        r'^[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}[:-]{1}[0-9A-Fa-f]{2}$',
        r'^[0-9A-Fa-f]{12}$',
        r'^[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}\.[0-9A-Fa-f]{2}$',
    ]
    return any(re.match(pattern, mac) for pattern in patterns)


async def run_in_thread(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)


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
