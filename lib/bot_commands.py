from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChatMember
from lib.config_reader import config

bot_general_commands = [
    BotCommand(command='h', description='help message'),
    BotCommand(command='joke', description='{joke_type:optional} - get joke'),
    BotCommand(command='meme', description='{subreddit:optional} - get meme from reddit'),
    BotCommand(command='ask', description='{prompt:optional} - ask AI'),
    BotCommand(command='change_llm_model', description='{model:required} - change llm model'),
    BotCommand(command='change_llm_key', description='{api_key:required} - change llm api key'),
    BotCommand(command='geoip', description='{ip:required} - get geoip'),
    BotCommand(command='gamble', description='{bet: optional} some gambling'),
    BotCommand(command='galton', description='{bet: optional, balls: optional} galton board'),
    BotCommand(command='blackjack', description='{bet: optional} blackjack'),
    BotCommand(command='roulette', description='{bet: optional} roulette'),
    BotCommand(command='balance', description='show gambling balance'),
    BotCommand(command='transfer', description='{amount: required, user: optional} - make transfer'),
    BotCommand(command='daily_prize', description='obtain daily prize'),
    BotCommand(command='ledger', description='show blockchain transactions'),
    BotCommand(command='blocks', description='show blockchain blocks'),
    BotCommand(command='total_pending_fees', description='show total fees of pending transactions'),
    BotCommand(command='user_blocks', description='{user: optional} show blockchain user blocks'),
    BotCommand(command='leaderboard', description='show leaderboard'),
    BotCommand(command='export_transactions', description='export all transactions in csv file'),
    BotCommand(command='mine', description='{nonce: required} attempt to mine block by yourself'),
    BotCommand(command='mine_block', description='force block mining for genesis user'),
    BotCommand(command='explore_block', description='{height: required} explore block'),
    BotCommand(command='user_stats', description='{user: optional} get user stats'),
    BotCommand(command='global_stats', description='get global stats'),
    BotCommand(command='galton_background', description='set galton board background'),
]

bot_admin_commands = [
    BotCommand(command='upload_faq', description='upload faq file'),
    BotCommand(command='faq', description='get faq file'),
    BotCommand(command='logs', description='get logs'),
    BotCommand(command='clear_videos', description='clear downloaded videos'),
    BotCommand(command='access', description='{otp_code:required} get privileged access'),
    BotCommand(
        command='download',
        description='{url:optional} - download video, if url not provided, you should reply to message containing url'
    ),
    BotCommand(command='clear_videos', description='clear downloaded videos'),
    BotCommand(
        command='delete_video',
        description='{filename:optional} - delete video, if filename not provided, you should reply to message containing filename'
    ),
    BotCommand(command='cookies', description='{reset: optional} add cookies.txt for yt-dlp'),
]

bot_admin_commands += bot_general_commands


def commands_to_text(commands: list[BotCommand]):
    return '\n'.join([f"/{c.command} {c.description}" for c in commands])


text_bot_general_commands = commands_to_text(bot_general_commands)
text_bot_admin_commands = commands_to_text(bot_admin_commands)


async def set_bot_commands(bot: Bot):
    await bot.set_my_commands(bot_general_commands)

    for group_id in config.group_ids:
        for admin_id in config.admin_ids:
            scope = BotCommandScopeChatMember(chat_id=group_id, user_id=admin_id)
            await bot.set_my_commands(bot_admin_commands, scope=scope)
