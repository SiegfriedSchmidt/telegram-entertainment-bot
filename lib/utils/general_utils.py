import asyncio
import os
from datetime import datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from typing import List, Tuple, ParamSpec, TypeVar, Callable


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


def get_size_str(size: int) -> str:
    return f'{round(size / 1024 / 1024, 1)} MB'


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


def from_iso(timestamp: str) -> str:
    return datetime.strftime(datetime.fromisoformat(timestamp), "%Y-%m-%d %H:%M:%S")


def clean_username(username: str) -> str:
    return username.replace("@", "").strip()


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


P = ParamSpec("P")
R = TypeVar("R")


async def run_in_thread(func: Callable[P, R], *args: P.args) -> R:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)
