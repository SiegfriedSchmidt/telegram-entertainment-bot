import asyncio
from lib.downloader import VideoInfo
from lib.downloader import downloader
from lib.config_reader import config
from aiogram import Router, F
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, LinkPreviewOptions
from lib.workers import workers

router = Router()
router.inline_query.filter(
    F.from_user.id.in_(config.admin_ids)
)


async def show_text(inline_query: InlineQuery, title: str, text: str) -> None:
    await inline_query.answer(results=[
        InlineQueryResultArticle(
            id="default",
            title=title,
            input_message_content=InputTextMessageContent(message_text=text),
        )
    ])


@router.inline_query()
async def inline_handler(inline_query: InlineQuery):
    query = inline_query.query.strip()
    if not query:
        return await show_text(inline_query, "Invalid", "No query provided")

    url = query.split()[0]
    info = await workers.enqueue(downloader.prepare_info, url)  # type: VideoInfo
    main_loop = asyncio.get_running_loop()
    asyncio.run_coroutine_threadsafe(workers.enqueue(downloader.download_video, info), main_loop)

    preview_url = info.url

    if "instagram.com" in preview_url:
        preview_url = (
            preview_url
            .replace("www.instagram.com", "kkinstagram.com")
            .replace("instagram.com", "kkinstagram.com")
        )
    elif "youtube.com" in preview_url or "youtu.be" in preview_url:
        preview_url = (
            preview_url
            .replace("www.youtube.com", "koutube.com")
            .replace("youtube.com", "koutube.com")
            .replace("youtu.be", "koutu.be")
        )
    else:
        preview_url = None

    results = [
        InlineQueryResultArticle(
            id="1",
            title=f"Open Video",
            description="Click to open video",
            # thumbnail_url="https://picsum.photos/200",
            input_message_content=InputTextMessageContent(
                message_text=info.server_url + f"\n\n({url})",
                link_preview_options=LinkPreviewOptions(
                    url=preview_url,
                    is_disabled=False,
                    prefer_large_media=True,
                    show_above_text=True
                ),
            ),
        )
    ]

    return await inline_query.answer(results=results)
