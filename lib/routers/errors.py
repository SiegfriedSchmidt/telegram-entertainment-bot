from aiogram import Router
from aiogram.types import ErrorEvent
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from lib.ledger.ledger import LedgerError
from lib.logger import main_logger

router = Router()


@router.errors()
async def error_handler(event: ErrorEvent):
    exception = event.exception

    if isinstance(exception, TelegramBadRequest):
        error_text = str(exception).lower()
        if "can't parse" in error_text:
            await safe_send(event.update, "Bot tried to send something weird. Skipping...")
        elif "message is empty" in error_text:
            await safe_send(event.update, "Empty message – nothing to send!")
        elif "caption is too long" in error_text:
            await safe_send(event.update, "That caption was too long for Telegram!")
        else:
            await safe_send(event.update, f"Telegram rejected the message. {str(exception)}")
    elif isinstance(exception, TelegramAPIError):
        await safe_send(event.update, f"Telegram server is having a moment. {str(exception)}")
    elif isinstance(exception, RuntimeError) or isinstance(exception, LedgerError):
        return await event.update.message.reply(str(exception))
    else:
        await safe_send(event.update, f"Unknown error occurred. {str(exception)}")

    return main_logger.exception("Telegram error caught globally", exc_info=exception)


async def safe_send(update, text: str):
    try:
        if update.message:
            await update.message.answer(text[:4000])
        elif update.callback_query:
            await update.callback_query.message.answer(text[:4000])
    except Exception as e:
        main_logger.error(e, exc_info=True)
