from aiogram import Router, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from dataclasses import fields
from typing import get_type_hints
from lib import database
from lib.config_reader import config
from lib.ledger import Ledger
from lib.router_factories import admin_commands, general_commands, messages
from lib.states.confirmation_state import ConfirmationState
from lib.storage import storage, PersistentData
from lib.utils.message_utils import get_args

router = Router()
router.message.filter(
    F.chat.type.in_(["private"]),
    F.chat.id.in_(config.admin_ids),
    F.from_user.id.in_(config.admin_ids)
)

router.include_routers(
    admin_commands.create_router(),
    general_commands.create_router(),
    messages.create_router()
)


@router.message(Command("config"))
async def cmd_config(message: types.Message, command: CommandObject):
    args = get_args(command)
    if len(args) != 2:
        current = {
            f.name: getattr(storage, f.name) for f in fields(PersistentData)
        }
        lines = ["Current configuration:"]
        for k, v in sorted(current.items()):
            lines.append(f"  {k:<32} = {v}")
        lines.append("")
        lines.append("Usage: /config <field> <value>")
        return await message.answer(f"```{'\n'.join(lines)}```", parse_mode='MarkdownV2')

    field_name = args[0]
    value_str = args[1]

    if not hasattr(storage, field_name):
        return await message.answer(f"Unknown setting: {field_name}")

    # Get expected type from type hints
    hints = get_type_hints(PersistentData)
    expected_type = hints.get(field_name)

    if expected_type is None:
        return await message.answer(f"Cannot determine type for field {field_name}")

    try:
        # Convert string -> correct type
        if expected_type is bool:
            value = value_str.lower() in {'true', '1', 'yes', 'on', 't', 'enable', 'enabled'}
        elif expected_type is int:
            value = int(value_str)
        elif expected_type is float:
            value = float(value_str)
        elif expected_type is str:
            value = value_str
        else:
            return await message.answer(f"Type {expected_type.__name__} not supported yet for {field_name}")

        old_value = getattr(storage, field_name)
        setattr(storage, field_name, value)

        return await message.answer(
            f"```{field_name} updated\n"
            f"  Old: {old_value}\n"
            f"  New: {value}\n"
            f"  Saved to: {storage.filename}```",
            parse_mode='MarkdownV2'
        )
    except ValueError as e:
        return await message.answer(f"Cannot convert '{value_str}' to {expected_type.__name__}:\n{e}")
    except Exception as e:
        return await message.answer(f"Error while updating: {type(e).__name__}: {e}")


@router.message(Command("send"))
async def send_cmd(message: types.Message, command: CommandObject, state: FSMContext):
    await state.set_state(ConfirmationState.admin_send_confirmation)
    await state.update_data(message=command.args)
    return await message.answer('Do you want to continue (y/n)?')


@router.message(ConfirmationState.admin_send_confirmation)
async def send(message: types.Message, state: FSMContext):
    if message.text == "y":
        state_message = (await state.get_data()).get("message")
        if not state_message:
            return await message.answer('Sorry, message is empty for some reason.')

        await message.answer('sending message...')
        await message.bot.send_message(config.main_group_id, state_message)
    else:
        await message.answer('abort')
    return await state.clear()


@router.message(Command("tx"))
async def tx_cmd(message: types.Message, command: CommandObject, ledger: Ledger):
    args = get_args(command, 4)
    if not args[2].isdecimal():
        return await message.answer('Invalid type of arguments.')

    tx = ledger.record_transaction(*args[:3], " ".join(args[3:]))
    return await message.answer(
        f'Transaction: {tx.from_user} -> {tx.to_user}: {tx.amount}, {tx.description} - recorded!'
    )


@router.message(Command("import_transactions"))
async def import_transactions_cmd(message: types.Message, ledger: Ledger):
    if not message.reply_to_message:
        return await message.answer("You should reply to a message with document.")
    if not message.reply_to_message.document:
        return await message.answer("You should reply to a message containing document.")

    doc = message.reply_to_message.document
    file = await message.bot.get_file(doc.file_id)
    downloaded_file = await message.bot.download_file(file.file_path)
    count = ledger.import_transactions_csv(downloaded_file)
    return await message.answer(f"Total imported transactions: {count}")


@router.message(Command("delete_pending"))
async def delete_pending_cmd(message: types.Message, ledger: Ledger):
    count = ledger.delete_pending_transactions()
    return await message.answer(f"Total deleted pending transactions: {count}")


@router.message(Command("reset_daily"))
async def reset_daily_cmd(message: types.Message, command: CommandObject):
    args = get_args(command, 1, 1)

    username = args[0]
    if not database.is_user_exists(username):
        return await message.answer(f"User {username} doesn't exist!")

    database.reset_daily_prize_time_for_user(username)
    return await message.answer(f"Daily prize time for user {username} has been reset!")
