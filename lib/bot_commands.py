from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChatMember

from lib.config_reader import config

bot_general_commands = [
    BotCommand(command='h', description='help message'),
    BotCommand(command='joke', description='{joke_type:optional} - get joke'),
    BotCommand(command='meme', description='{subreddit:optional} - get meme from reddit'),
    BotCommand(command='ask', description='{prompt:required} - ask AI'),
    BotCommand(command='geoip', description='{ip:required} - get geoip'),
    BotCommand(command='gamble', description='{bet: optional} some gambling'),
    BotCommand(command='galton', description='{bet: optional, balls: optional} some galton board gambling'),
    BotCommand(command='balance', description='show gambling balance'),
    BotCommand(command='transfer', description='{amount: required, username: optional} - make transfer'),
    BotCommand(command='daily_prize', description='obtain daily prize'),
    BotCommand(command='ledger', description='show blockchain transactions'),
    BotCommand(command='blocks', description='show blockchain blocks'),
    BotCommand(command='leaderboard', description='show leaderboard'),
    BotCommand(command='export_transactions', description='export all transactions in csv file'),
    BotCommand(command='mine_block', description='force mining for genesis user'),
    BotCommand(command='mine_block_attempt', description='{nonce: required} attempt to mine by yourself'),
    BotCommand(command='explore_block', description='{height: required} explore block'),
    BotCommand(command='user_stats', description='{username: optional} get user stats'),
    BotCommand(command='global_stats', description='get global stats'),
]

bot_admin_commands = [
    BotCommand(command='projects', description='show all docker projects'),
    BotCommand(command='up', description='{project_name:required} - start docker project'),
    BotCommand(command='down', description='{project_name:required} - stop docker project'),
    BotCommand(command='update', description='update bot image'),
    BotCommand(command='reboot', description='reboot machine'),
    BotCommand(command='prune', description='remove unused docker containers'),
    BotCommand(command='stats', description='host statistics'),
    BotCommand(command='upload_faq', description='upload faq file'),
    BotCommand(command='faq', description='get faq file'),
    BotCommand(command='logs', description='get logs'),
    BotCommand(command='curl', description='curl command'),
    BotCommand(command='torip', description='get tor geoip'),
    BotCommand(command='openconnect', description='{status|restart|stop|start:required} manage openconnect service'),
    BotCommand(command='del', description='delete replied message'),
    BotCommand(command='access', description='{otp_code:required} get privileged access'),
    BotCommand(command='activate', description='{terminal_type:optional} activate ssh session in text|image terminal'),
    BotCommand(command='deactivate', description='deactivate ssh session'),
    BotCommand(
        command='download',
        description='{url:optional} - download video, if url not provided, you should reply to message containing url'
    ),
    BotCommand(command='clear_videos', description='clear downloaded videos'),
    BotCommand(
        command='delete_video',
        description='{filename:optional} - delete video, if filename not provided, you should reply to message containing filename'
    ),
    BotCommand(command='switch', description='switch to another ssh host'),
    BotCommand(command='wol', description='{mac: required} wake on lan'),
    BotCommand(command='follow_file', description='{location: required} follow file'),
    BotCommand(command='unfollow_file', description='stop following current file'),
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
