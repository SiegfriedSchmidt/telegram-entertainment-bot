"""Dev-only harness: runs the project's real blackjack code outside the bot.

Nothing here is imported by the bot. The game, the renderer and `base.py` are loaded from the
project itself; only the money and the database are faked, so a simulation never touches them.

Layout it expects (project root = parent of `tools/`):

    assets/blackjack/background.png
    assets/blackjack/cards/{C,D,H,S}{1..13}.png, 1.png
    lib/gambling/base.py
    lib/gambling/blackjack_rendering.py
    lib/gambling/games/BlackjackGame.py
    lib/keyboards/blackjack_keyboard.py
"""
import importlib
import importlib.util
import sys
import tempfile
import types
from enum import Enum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------- fakes
class Handle:
    """Stand-in for lib.ledger.state_manager.FreezeHandle."""

    def __init__(self, ledger, amount):
        self.ledger, self.amount, self.released = ledger, amount, False

    def release(self):
        if not self.released:
            self.released = True
            self.ledger.balance += self.amount


class FakeLedger:
    """Same interface as lib.ledger.ledger.Ledger, but the balance lives and dies in this process."""

    def __init__(self, balance: int = 10 ** 9):
        self.balance = balance

    def get_user_balance(self, user_id):
        return self.balance

    def calc_fee(self, bet):
        return bet, 0

    def freeze(self, user_id, bet):
        self.balance -= bet
        return Handle(self, bet)

    def record_deposit(self, **kwargs):
        pass

    def record_gain(self, **kwargs):
        pass


class User:
    """Stand-in for lib.temporal_storage.UserProfile: the game only needs .id and .blackjack_bet."""

    def __init__(self, user_id: int = 1, blackjack_bet: int = 100):
        self.id = user_id
        self.blackjack_bet = blackjack_bet

    def __str__(self):
        return "player"


class BlackjackResultType(str, Enum):
    win = "win"
    blackjack = "blackjack"
    draw = "draw"
    lose = "lose"
    bust = "bust"
    surrender = "surrender"


class StatsType(str, Enum):
    blackjack_win = "blackjack_win"
    blackjack_all = "blackjack_all"


def _paste(frame, image, pos):
    """Fallback for lib.utils.cv2_utils.cv2_paste_with_alpha (no alpha blending)."""
    x, y = pos
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(frame.shape[1], x + image.shape[1]), min(frame.shape[0], y + image.shape[0])
    if x1 > x0 and y1 > y0:
        frame[y0:y1, x0:x1] = image[y0 - y:y1 - y, x0 - x:x1 - x, :frame.shape[2]]


# ------------------------------------------------------------------- loading
def _stub(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _import_or_stub(name: str, **attrs) -> types.ModuleType:
    """Take the project's module, or a stand-in when importing it drags the whole bot in."""
    try:
        return importlib.import_module(name)
    except Exception:
        return _stub(name, **attrs)


def _load(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_game(root: Path = ROOT):
    """Import the real game. Returns (BlackjackGame module, blackjack_rendering module)."""
    sys.path.insert(0, str(root))

    # the two things a simulation must never touch
    _stub("lib.database", update_user_stats=lambda *a, **k: None)
    _stub("lib.ledger.ledger", Ledger=FakeLedger)
    _stub("lib.ledger.state_manager", FreezeHandle=Handle)

    _import_or_stub("lib.models", MONEY_TYPE=int, BlackjackResultType=BlackjackResultType,
                    StatsType=StatsType)
    _import_or_stub("lib.temporal_storage", UserProfile=User)
    _import_or_stub("lib.utils.cv2_utils", cv2_paste_with_alpha=_paste)
    _import_or_stub("lib.init", blackjack_assets_folder_path=root / "assets/blackjack",
                    tmp_folder_path=root / "tools/out")

    for name in ["lib", "lib.gambling", "lib.gambling.games", "lib.ledger"]:
        if name not in sys.modules:
            _stub(name)
    sys.modules["lib"].database = sys.modules["lib.database"]

    _load("lib.gambling.base", root / "lib/gambling/base.py")
    rendering = _load("lib.gambling.blackjack_rendering", root / "lib/gambling/blackjack_rendering.py")
    game = _load("lib.gambling.games.BlackjackGame", root / "lib/gambling/games/BlackjackGame.py")

    # screenshots are the one side effect the tools do not want: send them to a throwaway directory
    tmp = Path(tempfile.mkdtemp(prefix="blackjack-tools-"))
    rendering.tmp_folder_path = game.tmp_folder_path = tmp
    return game, rendering


def new_game(blackjack_cls, bet: int = 100, balance: int = 10 ** 9, order: list[str] = None):
    """A dealt game. `order` = the exact sequence the cards come off the deck:
    dealer, dealer, player, player, then whatever the round needs."""
    game = blackjack_cls(FakeLedger(balance), User(1, bet), bet)
    if order is not None:
        game.deck = list(reversed(order))
    game.start()
    return game
