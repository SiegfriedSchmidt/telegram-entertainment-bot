from itertools import chain

from lib.ledger import Ledger


def get_leaderboard(ledger: Ledger, is_all=False):
    balances = ledger.get_all_balances() if is_all else ledger.get_all_balances()[1:]

    lines = chain(
        (f"<b>Leaderboard:</b>",),
        (f'{idx if is_all else idx + 1}. {username}: {amount}' for idx, (username, amount) in enumerate(balances))
    )
    return lines
