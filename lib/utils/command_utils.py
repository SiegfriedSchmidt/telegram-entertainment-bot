from aiogram import types
from aiogram.types import LinkPreviewOptions, FSInputFile, InputMediaVideo
from lib.downloader import downloader
from lib.keyboards.link_keyboard import get_link_keyboard
from lib.storage import storage
from lib.utils.general_utils import get_size_str


async def download_video(message: types.Message, url: str):
    answer = await message.reply("Downloading...")

    async def callback(text: str):
        await answer.edit_text(text)

    result, error = await downloader.download(url, callback)
    if error:
        return await answer.edit_text(f"Download failed: {error}")

    filepath, filename, server_url, optimized = result
    filesize = filepath.stat().st_size

    caption = f"{filename} {get_size_str(filesize)}{(' (optimized)' if optimized else '')}"
    if server_url and filesize > storage.video_max_size:
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
        return await answer.edit_media(media)
