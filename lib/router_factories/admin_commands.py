import asyncio
import os
import time
from io import BytesIO
from itertools import chain
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, BufferedInputFile, ReplyKeyboardRemove, InputMediaVideo, LinkPreviewOptions
from aiogram.utils.chat_action import ChatActionMiddleware
from rcon.source import rcon
from lib.api.geoip_api import geoip
from lib.downloader import downloader
from lib.init import data_folder_path, videos_folder_path, cookies_file_path
from lib.keyboards.switch_host_keyboard import get_switch_host_keyboard
from lib.logger import log_stream
from lib.matplotlib_tables import create_table_matplotlib
from lib.middlewares.user_middleware import UserMiddleware
from lib.models import TerminalType
from lib.temporal_storage import User
from lib.otp_manager import otp_manager, OTP_ACCESS_GRANTED_HOURS
from lib.ssh_manager import ssh_manager
from lib.states.confirmation_state import ConfirmationState
from lib.states.ssh_session_state import SSHSessionState
from lib.states.switch_state import SwitchState
from lib.utils.general_utils import run_in_thread, get_dir_size, clear_dir_contents, \
    remove_file, \
    is_valid_mac_address
from lib.utils.message_utils import get_args, save_document, large_respond


def create_router():
    router = Router()
    router.message.middleware(ChatActionMiddleware())
    router.message.middleware(UserMiddleware())

    @router.message(Command("stats"))
    async def stats_cmd(message: types.Message, user: User):
        answer = await message.answer("gathering statistics...")
        containers_ps, containers_stats, ram, cpu, uptime = await run_in_thread(ssh_manager[user.host].get_stats)

        containers_data = {}
        for c in containers_ps:
            containers_data[c["Names"]] = c

        for c in containers_stats:
            containers_data[c["Name"]] |= c

        headers = ["Name", "Image", "CPUPerc", "MemUsage", "Status"]
        data = []
        for c in containers_data.values():
            data.append([c["Name"], c["Image"], c["CPUPerc"], c["MemUsage"].split(' /')[0], c["Status"]])

        table_containers_image = create_table_matplotlib(data, headers)
        file = BufferedInputFile(table_containers_image.read(), filename="img.png")

        await answer.delete()
        await message.answer_photo(file, caption=f'Stats {time.strftime("%Y-%m-%d %H:%M:%S")}')

    @router.message(Command("projects"))
    async def projects_cmd(message: types.Message, user: User):
        docker_projects = ssh_manager[user.host].get_docker_projects()
        await message.answer('\n'.join(docker_projects))

    @router.message(Command("up"))
    async def up_cmd(message: types.Message, command: CommandObject, user: User):
        args = get_args(command, 1, 1)
        error = ssh_manager[user.host].up_project(args[0])
        if error:
            return await message.answer(error)
        return await message.answer('good')

    @router.message(Command("down"))
    async def down_cmd(message: types.Message, command: CommandObject, user: User):
        args = get_args(command, 1, 1)
        if args[0] == "telegram-ssh-bot":
            return await message.answer("Nah, you won't do that!")

        error = ssh_manager[user.host].down_project(args[0])
        if error:
            return await message.answer(error)
        return await message.answer('good')

    @router.message(Command("prune"))
    async def prune_cmd(message: types.Message, user: User):
        result = ssh_manager[user.host].docker_prune()
        return await large_respond(message, result)

    @router.message(Command("update"))
    async def update_cmd(message: types.Message, state: FSMContext):
        await state.set_state(ConfirmationState.update_confirmation)
        return await message.answer('Do you want to continue (y/n)?')

    @router.message(ConfirmationState.update_confirmation)
    async def update(message: types.Message, user: User, state: FSMContext):
        if message.text == "y":
            await message.answer('performing image update...')
            bot_update_log_file = ssh_manager[user.host].update()

            async def callback(text: str):
                await large_respond(message, text)

            asyncio.create_task(ssh_manager[user.host].follow_file(bot_update_log_file, callback, 5))
        else:
            await message.answer('abort')
        return await state.clear()

    @router.message(Command("reboot"), flags={'otp': True})
    async def reboot_cmd(message: types.Message, state: FSMContext):
        await state.set_state(ConfirmationState.reboot_confirmation)
        return await message.answer('Do you want to continue (y/n)?')

    @router.message(ConfirmationState.reboot_confirmation)
    async def reboot(message: types.Message, user: User, state: FSMContext):
        if message.text.lower() == "bipki":
            await message.answer('performing reboot...')
            ssh_manager[user.host].reboot()
        else:
            await message.answer('abort')
        return await state.clear()

    @router.message(Command("upload_faq"))
    async def upload_faq_cmd(message: types.Message):
        if not message.reply_to_message or not message.reply_to_message.document:
            return await message.answer("reply to a message with faq.md!")

        await save_document(message, data_folder_path / "faq.md")
        return await message.answer('Saved faq.md')

    @router.message(Command('cookies'))
    async def cookies_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 0, 1)
        if len(args) == 1 and args[0] == 'reset':
            downloader.cookies = None
            try:
                remove_file(cookies_file_path)
            except FileNotFoundError:
                return await message.answer("Cookies.txt not exists!")
            return await message.answer('Cookies reset!')

        if not message.reply_to_message or not message.reply_to_message.document:
            return await message.answer('reply to a message with cookies.txt!')

        await save_document(message, cookies_file_path)
        downloader.cookies = cookies_file_path
        return await message.answer('Saved cookies.txt')

    @router.message(Command("faq"))
    async def faq_cmd(message: types.Message):
        if not os.path.exists(f"{data_folder_path}/faq.md"):
            return await message.answer("'faq.md' not found.")

        document = FSInputFile(f"{data_folder_path}/faq.md", filename="faq.md")
        return await message.answer_document(document, caption=f"FAQ")

    @router.message(Command("logs"))
    async def logs_cmd(message: types.Message):
        file = BufferedInputFile(log_stream.get_file().read(), filename="logs.txt")
        return await message.answer_document(file)

    @router.message(Command("curl"), flags={'otp': True})
    async def curl_cmd(message: types.Message, user: User, command: CommandObject):
        result, error = ssh_manager[user.host].curl(command.args)
        if not result:
            return await message.answer(error)
        return await message.answer(result)

    @router.message(Command("torip"))
    async def torip_cmd(message: types.Message, user: User):
        result, error = ssh_manager[user.host].curl('eth0.me --connect-timeout 5 --proxy http://192.168.192.1:18082')
        if not result:
            return await message.answer(error)

        try:
            json = await geoip(result)
            text = '\n'.join(f"{key}: {val}" for key, val in json.items())
        except Exception as e:
            return await message.answer(str(e))

        return await message.answer(text)

    # @router.message(Command("del"))
    # async def del_cmd(message: types.Message):
    #     if not message.reply_to_message:
    #         return await message.answer("You need to reply to a message to delete.")
    #
    #     try:
    #         return await message.reply_to_message.delete()
    #     except TelegramBadRequest:
    #         return await message.answer("I have no permission to delete this message.")

    @router.message(Command("openconnect"))
    async def openconnect_cmd(message: types.Message, command: CommandObject, user: User):
        args = get_args(command, 1, 1)
        if args[0] not in ['status', 'restart', 'stop', 'start']:
            return await message.answer('invalid syntax, openconnect status|restart|stop|start')

        result, error = ssh_manager[user.host].openconnect(args[0])
        if not result:
            return await large_respond(message, error)
        return await large_respond(message, result)

    @router.message(Command("access"))
    async def access_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 1, 1)
        result = otp_manager.authenticate(message.from_user.id, args[0])
        if result:
            return await message.answer(result)
        return await message.answer(f'Access granted for {OTP_ACCESS_GRANTED_HOURS} hours.')

    def stdout_callback_image_generator(message: types.Message):
        async def stdout_callback(chunk: BytesIO):
            try:
                input_file = BufferedInputFile(chunk.read(), filename="terminal.png")
                await message.answer_photo(input_file)
            except Exception as e:
                await message.answer(str(e))

        return stdout_callback

    def stdout_callback_text_generator(message: types.Message):
        async def stdout_callback(chunk: str):
            if not chunk:
                return
            try:
                await message.answer(f'```bash\n{chunk}```', parse_mode='Markdown')
            except Exception as e:
                await message.answer(str(e))

        return stdout_callback

    @router.message(Command("activate"), flags={'otp': True})
    async def activate_cmd(message: types.Message, state: FSMContext, user: User, command: CommandObject):
        terminal_type = 'text'
        args = get_args(command, 0, 1)
        if len(args) == 1:
            terminal_type = args[0]
            if terminal_type not in TerminalType:
                return await message.answer('Invalid terminal type! Should be text|image.')

        await message.answer(f'SSH session activated in {terminal_type} terminal! To deactivate enter /deactivate\n')
        await state.set_state(SSHSessionState.session_activated)
        ssh_session = ssh_manager.interactive_session(user.host, terminal_type)
        await ssh_session.connect(
            stdout_callback_text_generator(message) if terminal_type == TerminalType.text else
            stdout_callback_image_generator(message)
        )
        return await state.update_data(ssh_session=ssh_session)

    @router.message(Command("download"))
    async def download_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 0, 1)
        if message.reply_to_message:
            url = message.reply_to_message.text
        elif len(args) == 1:
            url = args[0]
        else:
            return await message.answer('There is no url to download!')

        answer = await message.answer("Downloading...")
        result, error = await run_in_thread(downloader.download, url)
        if error:
            return await answer.edit_text(f"Download failed: {error}")

        filepath, filename, server_url, info = result
        if server_url:
            # media = InputMediaVideo(media=server_url, caption=filename, supports_streaming=True)
            return await answer.edit_text(
                filename,
                link_preview_options=LinkPreviewOptions(
                    url=server_url,
                    is_disabled=False,
                    prefer_large_media=True,
                    show_above_text=True
                ),
                disable_web_page_preview=False
            )
        else:
            video = FSInputFile(filepath, filename=filename)
            media = InputMediaVideo(media=video, caption=filename)
            return await answer.edit_media(media)

    @router.message(Command("clear_videos"))
    async def clear_videos_cmd(message: types.Message, state: FSMContext):
        space = round(get_dir_size(videos_folder_path) / 1024 / 1024, 1)
        if space < 1:
            return await message.answer("Directory is empty.")
        await state.set_state(ConfirmationState.clear_videos_confirmation)
        return await message.answer(f'Do you want to delete all videos (y/n)? Space will be freed: {space} MB.')

    @router.message(ConfirmationState.clear_videos_confirmation)
    async def clear_videos(message: types.Message, state: FSMContext):
        if message.text.lower() == "y":
            files = clear_dir_contents(videos_folder_path)
            text = map(lambda t: f"{t[0]}: {round(t[1] / 1024 / 1024, 1)} MB", files)
            await large_respond(message, chain(("Files deleted:",), text))
        else:
            await message.answer('abort')
        return await state.clear()

    @router.message(Command("delete_video"))
    async def delete_video_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 0, 1)
        if message.reply_to_message:
            filename = message.reply_to_message.text
            if not filename:
                filename = message.reply_to_message.caption
        elif len(args) == 1:
            filename = args[0]
        else:
            return await message.answer('There is no video to delete!')

        try:
            filesize = remove_file(videos_folder_path / filename)
            await message.answer(f'Video {filename} - {round(filesize / 1024 / 1024, 1)} MB deleted.')
        except FileNotFoundError:
            return await message.answer('Video not found!')

    @router.message(Command("switch"))
    async def switch_cmd(message: types.Message, state: FSMContext):
        await state.set_state(SwitchState.switching)
        await message.answer(
            f"Choose host:",
            reply_markup=get_switch_host_keyboard(ssh_manager.get_hosts())
        )

    @router.message(SwitchState.switching)
    async def switch(message: types.Message, user: User, state: FSMContext):
        await state.clear()
        try:
            user.host = message.text
        except KeyError as e:
            return await message.answer(str(e), reply_markup=ReplyKeyboardRemove())

        return await message.answer(f'Host has been switched to {user.host}!', reply_markup=ReplyKeyboardRemove())

    @router.message(Command("wol"))
    async def wol_cmd(message: types.Message, command: CommandObject, user: User):
        args = get_args(command, 1, 1)
        if not is_valid_mac_address(args[0]):
            return await message.answer('invalid syntax, wakeonlan {mac address}')

        result, error = ssh_manager[user.host].wakeonlan(args[0])
        if not result:
            return await large_respond(message, error)
        return await large_respond(message, result)

    @router.message(Command("follow_file"), flags={'otp': True})
    async def follow_file_cmd(message: types.Message, command: CommandObject, user: User):
        args = get_args(command, 1, 1)

        async def callback(text: str):
            await message.answer(text)

        location = args[0]
        asyncio.create_task(ssh_manager[user.host].follow_file(location, callback))
        return await message.answer(f'File "{location}" following activated! To deactivate do /unfollow_file')

    @router.message(Command("unfollow_file"))
    async def unfollow_file_cmd(message: types.Message, user: User):
        if not ssh_manager[user.host].following_file:
            return await message.answer('You are not following any file right now!')
        ssh_manager[user.host].unfollow()
        return await message.answer(f'File following deactivated!')

    @router.message(Command("rcon_follow"))
    async def rcon_follow_cmd(message: types.Message, user: User):
        rcon_settings = ssh_manager.get_host(user.host).rcon
        if rcon_settings is None:
            return await message.answer("RCON settings not set!")

        rcon_text = '[Server thread/INFO] [net.minecraft.server.MinecraftServer/]:'
        rcon_text_len = len(rcon_text)

        async def callback(text: str):
            lines_raw = text.split('\n')
            lines = []
            for line_raw in lines_raw:
                idx = line_raw.find(rcon_text)
                if idx != -1:
                    line = line_raw[idx + rcon_text_len:]
                    if len(line) > 0:
                        lines.append(line)

            if len(lines) > 0:
                await large_respond(message, lines)

        asyncio.create_task(ssh_manager[user.host].follow_file(rcon_settings.rcon_logs_path, callback))
        return await message.answer(f'Rcon following activated! To deactivate do /unfollow_file')

    @router.message(Command('rcon'))
    async def rcon_cmd(message: types.Message, command: CommandObject, user: User):
        args = get_args(command, 1)
        rcon_settings = ssh_manager.get_host(user.host).rcon
        if rcon_settings is None:
            return await message.answer("RCON settings not set!")

        response = await rcon(*args, host=rcon_settings.address, port=rcon_settings.port, passwd=rcon_settings.password)
        if response:
            await message.answer(response)
        return None

    return router
