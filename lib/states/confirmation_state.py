from aiogram.fsm.state import StatesGroup, State


class ConfirmationState(StatesGroup):
    update_confirmation = State()
    reboot_confirmation = State()
    admin_send_confirmation = State()
    clear_videos_confirmation = State()
    transfer_confirmation = State()
    admin_call_confirmation = State()
    galton_background_confirmation = State()
