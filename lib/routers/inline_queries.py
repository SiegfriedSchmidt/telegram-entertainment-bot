from lib.downloader import downloader
from lib.utils.general_utils import run_in_thread
from lib.config_reader import config
from aiogram import Router, F
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent, LinkPreviewOptions

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
    result, error = await run_in_thread(downloader.download, url)
    if error:
        return await show_text(inline_query, "Error", "Error occurred while downloading")

    filepath, filename, server_url, info = result
    if not server_url:
        return await show_text(inline_query, "Error", "Error occurred while downloading")

    results = [
        InlineQueryResultArticle(
            id="1",
            title=f"Open Video",
            description="Click to open video",
            # thumbnail_url="https://picsum.photos/200",
            input_message_content=InputTextMessageContent(
                message_text=server_url,
                link_preview_options=LinkPreviewOptions(
                    url=server_url,
                    is_disabled=False,
                    prefer_large_media=True,
                    show_above_text=True
                ),
            ),
        )
    ]

    return await inline_query.answer(results=results)
