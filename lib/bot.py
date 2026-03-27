import asyncio
import nest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
# from aiogram.exceptions import TelegramBadRequest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from lib.api.joke_api import get_joke
# from lib.api.meme_api import get_meme
from lib.bot_commands import set_bot_commands
from lib.config_reader import config
from lib.gambler import Gambler
from lib.init import galton_videos_folder_path, bot_version, blackjack_videos_folder_path
from lib.ledger import Ledger, LedgerError
from lib.routers import public_commands, errors, group_admin, group_general, private_admin
from lib.logger import main_logger
from lib.middlewares.access_middleware import AccessMiddleware
from lib.middlewares.logger_middleware import LoggerMiddleware
from lib.ssh_manager import ssh_manager
from lib.storage import storage
from lib.utils.message_factories import get_leaderboard
from lib.utils.utils import clear_dir_contents

nest_asyncio.apply()


async def notification(message: str, bot: Bot):
    main_logger.info(message)
    if storage.notifications_enabled:
        await bot.send_message(config.main_group_id, message, parse_mode=None)


async def on_day_start(bot: Bot, ledger: Ledger) -> None:
    clear_dir_contents(galton_videos_folder_path)
    clear_dir_contents(blackjack_videos_folder_path)

    joke = await get_joke()
    message = f'Daily joke:\n\n{joke}'

    for group_id in config.group_ids:
        leaderboard = '\n'.join(get_leaderboard(ledger))
        await bot.send_message(
            group_id, f"<b>Daily Prize Updated!</b>. Do /daily_prize to open!\n{leaderboard}", parse_mode="html"
        )
        await asyncio.sleep(5)
        await bot.send_message(group_id, message, parse_mode=None)

    # url, caption = None, None
    # try:
    #     url, caption = await get_meme()
    # except Exception as e:
    #     main_logger.exception(e)
    #
    # for group_id in config.group_ids:
    #     await bot.send_message(group_id, "<b>Daily Prize Updated!</b>. Do /daily_prize to open!", parse_mode="html")
    #     await asyncio.sleep(5)
    #     if url is None or caption is None:
    #         continue
    #
    #     try:
    #         if url.endswith(('.jpg', '.jpeg', '.png', '.webp')):
    #             await bot.send_photo(group_id, url, caption=caption)
    #         elif url.endswith('.gif'):
    #             await bot.send_animation(group_id, url, caption=caption)
    #         elif url.endswith(('.mp4', '.gifv', '.webm')):
    #             await bot.send_video(group_id, url, caption=caption)
    #     except TelegramBadRequest:
    #         await asyncio.sleep(1)
    #         await bot.send_message(group_id, f"{url}\n\n{caption}", disable_web_page_preview=False)

    main_logger.info("Day start function executed.")


async def on_startup(bot: Bot, scheduler: AsyncIOScheduler, ledger: Ledger) -> None:
    # ledger
    me = await bot.get_me()
    ledger.genesis_username = me.username
    try:
        ledger.load_and_verify_chain()
    except LedgerError as e:
        await notification(str(e), bot)
        await bot.session.close()
        raise

    # scheduler
    hour, minute = map(int, config.day_start_time.split(":"))
    scheduler.add_job(on_day_start, CronTrigger(hour=hour, minute=minute), args=(bot, ledger))
    scheduler.add_job(ledger.mine_block, IntervalTrigger(seconds=storage.mine_block_interval_seconds))
    scheduler.start()

    # start message
    start_message = f"Bot {bot_version} started."

    # startup docker checks
    if storage.startup_docker_checks:
        containers_json = ssh_manager[config.main_host.get_secret_value()].get_running_containers()
        nextcloud_running = False
        for c in containers_json:
            if c["Image"] == 'nextcloud':
                nextcloud_running = True
        start_message += '' if nextcloud_running else " Nextcloud is NOT running. Launch it via '/up nextcloud'."

    await notification(start_message, bot)


async def on_shutdown(bot: Bot, scheduler: AsyncIOScheduler) -> None:
    scheduler.shutdown(wait=True)
    await notification("Bot stopped.", bot)


async def main():
    # logging.basicConfig(level=logging.DEBUG)
    bot = Bot(
        token=config.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=None, disable_notification=True),
        session=AiohttpSession(proxy=config.proxy_url if config.proxy_url else None)
    )

    # dispatcher
    dp = Dispatcher()

    # register startup/shutdown
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # middlewares
    dp.message.middleware(LoggerMiddleware())
    dp.message.middleware(AccessMiddleware())

    # routers
    dp.include_routers(
        errors.router,
        public_commands.router,
        group_admin.router,
        group_general.router,
        private_admin.router
    )

    await bot.delete_webhook(drop_pending_updates=True)
    await set_bot_commands(bot)

    # init shared classes
    scheduler = AsyncIOScheduler()
    ledger = Ledger(storage.mine_block_reward)
    gambler = Gambler(ledger)

    await dp.start_polling(
        bot, allowed_updates=dp.resolve_used_update_types(),
        scheduler=scheduler, ledger=ledger, gambler=gambler
    )


def start_bot():
    asyncio.run(main())
