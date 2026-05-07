import os
from itertools import chain
from aiogram import Router, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import FSInputFile, BufferedInputFile
from aiogram.utils.chat_action import ChatActionMiddleware
from lib.downloader import downloader
from lib.init import data_folder_path, videos_folder_path, cookies_file_path
from lib.logger import log_stream
from lib.middlewares.user_middleware import UserMiddleware
from lib.otp_manager import otp_manager, OTP_ACCESS_GRANTED_HOURS
from lib.states.confirmation_state import ConfirmationState
from lib.utils.command_utils import download_video
from lib.utils.general_utils import get_dir_size, clear_dir_contents, remove_file, get_size_str
from lib.utils.message_utils import get_args, save_document, large_respond


def create_router():
    router = Router()
    router.message.middleware(ChatActionMiddleware())
    router.message.middleware(UserMiddleware())

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

    @router.message(Command("access"))
    async def access_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 1, 1)
        result = otp_manager.authenticate(message.from_user.id, args[0])
        if result:
            return await message.answer(result)
        return await message.answer(f'Access granted for {OTP_ACCESS_GRANTED_HOURS} hours.')

    @router.message(Command("download"))
    async def download_cmd(message: types.Message, command: CommandObject):
        args = get_args(command, 0, 1)
        if message.reply_to_message:
            url = message.reply_to_message.text
            await download_video(message.reply_to_message, url)
        elif len(args) == 1:
            url = args[0]
            await download_video(message, url)
        else:
            await message.answer('There is no url to download!')

    @router.message(Command("clear_videos"))
    async def clear_videos_cmd(message: types.Message, state: FSMContext):
        dir_size = get_dir_size(videos_folder_path)
        if dir_size < 1:
            return await message.answer("Directory is empty.")
        await state.set_state(ConfirmationState.clear_videos_confirmation)
        return await message.answer(
            f'Do you want to delete all videos (y/n)? Space will be freed: {get_size_str(dir_size)}.'
        )

    @router.message(ConfirmationState.clear_videos_confirmation)
    async def clear_videos(message: types.Message, state: FSMContext):
        if message.text.lower() == "y":
            files = clear_dir_contents(videos_folder_path)
            text = map(lambda t: f"{t[0]}: {get_size_str(t[1])}", files)
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

        filename = filename.split()[0]
        try:
            filesize = remove_file(videos_folder_path / filename)
            await message.answer(f'Video {filename} - {round(filesize / 1024 / 1024, 1)} MB deleted.')
        except FileNotFoundError:
            return await message.answer('Video not found!')

    return router
