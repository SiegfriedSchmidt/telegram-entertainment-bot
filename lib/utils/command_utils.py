import asyncio

from aiogram import types
from aiogram.types import LinkPreviewOptions, FSInputFile, InputMediaVideo
from lib.downloader import downloader
from lib.keyboards.link_keyboard import get_link_keyboard
from lib.storage import storage
from lib.utils.general_utils import get_size_str
from lib.workers import workers


async def download_video(message: types.Message, url: str):
    answer = await message.reply("Downloading...")

    main_loop = asyncio.get_running_loop()

    async def edit_text_wrapper(text: str):
        await answer.edit_text(text)

    def callback(text: str):
        asyncio.run_coroutine_threadsafe(edit_text_wrapper(text), main_loop)

    result, error = await workers.enqueue(downloader.download, url, callback)
    if error:
        return await answer.edit_text(f"Download failed: {error}")

    filepath, filename, server_url, optimized = result
    filesize = filepath.stat().st_size

    caption = f"{filename} {get_size_str(filesize)}{(' (optimized)' if optimized else '')}"
    if filesize > storage.video_max_size:
        # media = InputMediaVideo(media=server_url, caption=filename, supports_streaming=True)
        return await answer.edit_text(
            caption,
            link_preview_options=LinkPreviewOptions(
                url=server_url,
                is_disabled=False,
                prefer_large_media=True,
                show_above_text=True
            ),
            reply_markup=get_link_keyboard(server_url)
        )
    else:
        video = FSInputFile(filepath, filename=filename)
        media = InputMediaVideo(media=video, caption=caption)
        return await answer.edit_media(media, reply_markup=get_link_keyboard(server_url))
