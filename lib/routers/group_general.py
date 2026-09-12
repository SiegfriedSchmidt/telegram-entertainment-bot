from lib.config_reader import config
from lib.router_factories import general_commands, blackjack_session, roulette_session, messages, reactions
from aiogram import F, Router

router = Router()
router.message.filter(
    F.chat.type.in_(["group", "supergroup"]),
    F.chat.id.in_(config.group_ids),
)

router.include_routers(
    roulette_session.create_router(),
    blackjack_session.create_router(),
    general_commands.create_router(),
    messages.create_router(),
    reactions.create_router()
)
