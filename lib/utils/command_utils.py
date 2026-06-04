import asyncio
from aiogram import types
from aiogram.types import LinkPreviewOptions, FSInputFile, InputMediaVideo
from lib.downloader import VideoInfo
from lib.downloader import downloader
from lib.keyboards.link_keyboard import get_link_keyboard
from lib.storage import storage
from lib.utils.general_utils import get_size_str
from lib.workers import workers


async def download_video(message: types.Message, url: str, constraint=False):
    answer = await message.reply("Getting info...")
    info = await workers.enqueue(downloader.prepare_info, url)  # type: VideoInfo

    if constraint and info.duration > storage.video_max_duration:
        return await answer.delete()

    if info.downloaded:
        result = "cached"
    else:
        await answer.edit_text("Downloading...")
        main_loop = asyncio.get_running_loop()

        async def edit_text_wrapper(text: str):
            await answer.edit_text(text)

        def callback(text: str):
            asyncio.run_coroutine_threadsafe(edit_text_wrapper(text), main_loop)

        error, result = await workers.enqueue(downloader.download_video, info, callback)  # type: bool, str
        if error:
            return await answer.edit_text(f"Download failed: {result}")

    filesize = info.video_path.stat().st_size
    caption = f"{info.video_path.name} {get_size_str(filesize)} {info.view_count}" + (f" ({result})" if result else "")
    if filesize > storage.video_max_size:
        # media = InputMediaVideo(media=server_url, caption=filename, supports_streaming=True)
        return await answer.edit_text(
            caption,
            link_preview_options=LinkPreviewOptions(
                url=info.server_url,
                is_disabled=False,
                prefer_large_media=True,
                show_above_text=True
            ),
            reply_markup=get_link_keyboard(info.server_url)
        )
    else:
        video = FSInputFile(info.video_path, filename=info.video_path.name)
        media = InputMediaVideo(media=video, caption=caption)
        return await answer.edit_media(media, reply_markup=get_link_keyboard(info.server_url))
