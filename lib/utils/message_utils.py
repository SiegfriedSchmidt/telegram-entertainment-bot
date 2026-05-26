import asyncio
import unicodeit
import sympy
from sympy.parsing.latex import parse_latex
from pathlib import Path
from typing import List, runtime_checkable, Protocol, Union, Iterable, Generator
from urllib.parse import quote
from aiogram import types
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject
from aiogram.types import ChatMemberAdministrator, ChatMemberOwner
from md2tgmd import escape


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


async def get_name_or_id_with_reply(message: types.Message, arg: str = None) -> str | int:
    if message.reply_to_message:
        name_or_id = message.reply_to_message.from_user.id
    elif arg is not None:
        name_or_id = arg
    else:
        name_or_id = message.from_user.id

    return name_or_id


async def get_question(message: types.Message, args: str = None) -> str:
    question = ''
    if args:
        question = args
    if message.reply_to_message and (message.reply_to_message.text or message.reply_to_message.caption):
        if question:
            question += " "
        if message.reply_to_message.text:
            question += message.reply_to_message.text
        if message.reply_to_message.caption:
            question += message.reply_to_message.caption

    return question


def latex_img_link(latex: str) -> str:
    return r"https://latex.codecogs.com/png.image?\dpi{200}" + latex


def embed_url(url: str) -> str:
    encoded_url = quote(url, safe="")
    return f"[\u200b]({encoded_url})"


def latex_to_text(latex: str) -> str:
    latex = latex.strip("$ \n")

    try:
        return unicodeit.replace(latex)
    except Exception:
        pass

    try:
        return sympy.pretty(parse_latex(latex), use_unicode=True)
    except Exception:
        pass

    return latex


@runtime_checkable
class Stringable(Protocol):
    def __str__(self) -> str: ...


def smart_split(text: str, max_length: int) -> Generator[str, None, None]:
    """
    Split `text` into chunks of at most `max_length` characters,
    preferring breaks at newlines, then spaces, then arbitrary positions.
    """
    if len(text) <= max_length:
        yield text
        return

    # 1. Try splitting by newlines first
    lines = text.split('\n')
    current_chunk = []
    current_len = 0

    for line in lines:
        # If a single line is longer than max_length, handle it with space/char split
        if len(line) > max_length:
            # Flush current chunk if any
            if current_chunk:
                yield '\n'.join(current_chunk)
                current_chunk = []
                current_len = 0
            # Recursively split the long line using spaces/characters
            for subchunk in split_long_line(line, max_length):
                yield subchunk
            continue

        # Check if adding this line (with a newline) would exceed the limit
        if current_chunk:
            candidate_len = current_len + 1 + len(line)  # +1 for the newline
        else:
            candidate_len = len(line)

        if candidate_len <= max_length:
            current_chunk.append(line)
            current_len = candidate_len
        else:
            # Flush current chunk and start a new one with this line
            if current_chunk:
                yield '\n'.join(current_chunk)
            current_chunk = [line]
            current_len = len(line)

    if current_chunk:
        yield '\n'.join(current_chunk)


def split_long_line(line: str, max_length: int) -> Generator[str, None, None]:
    """
    Split a single line that exceeds max_length.
    Prefer spaces, fall back to character split.
    """
    if len(line) <= max_length:
        yield line
        return

    # Try splitting by spaces
    words = line.split(' ')
    current_chunk = []
    current_len = 0

    for w in words:
        # If a single word is longer than max_length, we must split it by characters
        if len(w) > max_length:
            # Flush current word‑based chunk
            if current_chunk:
                yield ' '.join(current_chunk)
                current_chunk = []
                current_len = 0
            # Split the extra‑long word by characters
            for i in range(0, len(w), max_length):
                yield w[i:i + max_length]
            continue

        # Try to add the word (with a space if not first)
        if current_chunk:
            candidate = current_len + 1 + len(w)
        else:
            candidate = len(w)

        if candidate <= max_length:
            current_chunk.append(w)
            current_len = candidate
        else:
            # Flush and start new chunk with this word
            if current_chunk:
                yield ' '.join(current_chunk)
            current_chunk = [w]
            current_len = len(w)

    if current_chunk:
        yield ' '.join(current_chunk)


async def large_respond(message: types.Message, printable: Union[str, Iterable[Stringable | str]],
                        timeout=3, characters=4000, maximum=6, escape_md=True, **kwargs) -> bool:
    if not printable:
        await message.answer("Empty message.")
        return True
    elif isinstance(printable, str):
        string = printable if isinstance(printable, str) else str(printable)
    elif isinstance(printable, Iterable):
        string = '\n'.join(obj if isinstance(obj, str) else str(obj) for obj in printable)
    else:
        await message.answer("I've get smth else than a str or Iterable.")
        return False

    if kwargs.get("parse_mode", "") == "MarkdownV2" and escape_md:
        string = escape(string)

    for idx, chunk in enumerate(smart_split(string, characters)):
        if idx >= maximum:
            return True
        await message.answer(chunk, **kwargs)
        await asyncio.sleep(timeout)

    return True
