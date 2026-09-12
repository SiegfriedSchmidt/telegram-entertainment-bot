"""Dev-only: house edge of your blackjack rules, measured on the project's own game code.

    python3 tools/ev_sim.py                      # sweep the blackjack payout, pick one for ~1% (a few seconds)
    python3 tools/ev_sim.py 2.5                  # measure one payout
    python3 tools/ev_sim.py 2.0 2.25 2.5 -n 1e6  # compare payouts
    python3 tools/ev_sim.py --baseline           # also show hit/stand/surrender without split+double
    python3 tools/ev_sim.py --frames             # render sample hands into tools/out/

The payout sweep only changes BlackjackGame.BLACKJACK_MULTIPLIER for the duration of the run,
nothing is written to the project.
"""
import argparse
import random
import sys
from collections import Counter
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.bj_harness import FakeLedger, User, load_game, new_game

SWEEP = [2.0, 2.25, 2.3, 2.5]
TARGET_EDGE = 1.0                 # the house edge we are aiming for, in % of the initial bet


# ------------------------------------------------------------------ basic strategy (S17, DAS, LS)
def choose_action(game, advanced: bool = True) -> str:
    hand = game.active_hand
    actions = [a for a in game.get_available_actions() if advanced or a in ("hit", "stand", "surrender")]
    up = rendering.card_value(game.dealer_hand[0])
    up = 11 if up == 1 else up                       # the dealer's ace plays as 11
    values = [rendering.card_value(card) for card in hand.cards]
    hard = sum(values)
    soft = 1 in values and hard + 10 <= 21
    total = hard + 10 if soft else hard
    pair = len(values) == 2 and values[0] == values[1]

    if "surrender" in actions and not soft and (
            (total == 16 and up in (9, 10, 11)) or (total == 15 and up == 10)):
        return "surrender"

    if "split" in actions and pair:
        value = values[0]
        if value in (1, 8):
            return "split"
        if value == 9:
            return "split" if 2 <= up <= 9 and up != 7 else "stand"
        if value == 7:
            return "split" if up <= 7 else "hit"
        if value == 6:
            return "split" if up <= 6 else "hit"
        if value == 4:
            return "split" if up in (5, 6) else "hit"
        if value in (2, 3):
            return "split" if up <= 7 else "hit"

    if "double" in actions:
        if soft:
            if total in (17, 18) and 3 <= up <= 6:
                return "double"
            if total in (15, 16) and 4 <= up <= 6:
                return "double"
            if total in (13, 14) and up in (5, 6):
                return "double"
        else:
            if total == 11:
                return "double"
            if total == 10 and up <= 9:
                return "double"
            if total == 9 and 3 <= up <= 6:
                return "double"

    if soft:
        if total >= 19:
            return "stand"
        if total == 18:
            return "stand" if up in (2, 7, 8) else "hit"
        return "hit"

    if total >= 17:
        return "stand"
    if total >= 13:
        return "stand" if up <= 6 else "hit"
    if total == 12:
        return "stand" if 4 <= up <= 6 else "hit"
    return "hit"


def play_round(BlackjackGame, bet: int = 100, advanced: bool = True) -> tuple[float, Counter, int]:
    """Returns (profit for the player, result tally, number of hands dealt)."""
    game = new_game(BlackjackGame, bet)
    steps = 0
    while not game.finished:
        getattr(game, choose_action(game, advanced))()
        steps += 1
        if steps > 40:
            raise RuntimeError("the round did not finish")

    stake = sum(hand.bet for hand in game.hands)
    payout = sum(BlackjackGame._get_caption_and_multiplier(hand.result)[1] * hand.bet
                 for hand in game.hands)
    tally = Counter(hand.result.value for hand in game.hands)
    return payout - stake, tally, len(game.hands)


def simulate(BlackjackGame, rounds: int, advanced: bool = True) -> tuple[float, Counter, float, float]:
    """Returns (house edge in % of the initial bet, result tally, hands per round, naturals per round).

    Naturals matter twice: they are the only hands the blackjack payout touches, and they are always
    worth exactly one initial bet (a split hand is never a natural, and a doubled one is not either).
    So one run pins down the whole payout -> edge curve, not just one point on it.
    """
    net, tally, hands = 0, Counter(), 0
    for _ in range(rounds):
        profit, round_tally, round_hands = play_round(BlackjackGame, 100, advanced)
        net += profit
        tally += round_tally
        hands += round_hands
    return -net / (rounds * 100) * 100, tally, hands / rounds, tally["blackjack"] / rounds


def report(label, edge, tally, hands_per_round, rounds):
    se = 1.14 / (rounds ** 0.5) * 100
    dealt = sum(tally.values())
    naturals = 100 * tally["blackjack"] / dealt
    print(f"{label:<34} house edge {edge:+5.2f}% (±{se:.2f}%)   "
          f"blackjack {naturals:.2f}% of hands, {hands_per_round:.2f} hands/round", flush=True)


def payout_curve(edge, naturals, rounds, measured_at, multipliers):
    """Print the edge for every payout. Only the measured point carries sampling noise; the rest of
    the curve is exact, because raising the payout by 0.1 costs precisely (naturals per round) x 0.1."""
    se = 1.14 / (rounds ** 0.5) * 100
    slope = naturals * 100
    print(f"\nhouse edge {edge:+.2f}% (±{se:.2f}%) at X{measured_at:g} "
          f"over {rounds:,} rounds, {100 * naturals:.2f}% of them won with a natural."
          f" The rest of the curve is arithmetic, not another sample:\n")
    for multiplier in multipliers:
        value = edge - (multiplier - measured_at) * slope
        print(f"  blackjack pays X{multiplier:<5g} house edge {value:+5.2f}%"
              f"{'   <- measured' if multiplier == measured_at else ''}")

    target = measured_at + (edge - TARGET_EDGE) / slope
    print(f"\nfor a {TARGET_EDGE}% house edge: BLACKJACK_MULTIPLIER = {target:.2f} "
          f"(every +0.1 of the payout costs {slope / 10:.2f} points of edge)")


# ------------------------------------------------------------------ sample frames
def render_frames(module, out: Path) -> None:
    BlackjackGame, Hand = module.BlackjackGame, module.Hand

    def sample(name, hands, dealer, active):
        game = new_game(BlackjackGame)
        game.dealer_hand = dealer
        game.hands = [Hand(cards=cards, raw_bet=100, bet=100, from_split=len(hands) > 1)
                      for cards in hands]
        cv2.imwrite(str(out / f"{name}.png"), game.render_hands(dealer_open=True, active=active))

    sample("sample_1_hand", [["C10", "H9", "D2"]], ["S1", "H7"], None)
    sample("sample_2_hands", [["C8", "D8", "H5"], ["S9", "C9"]], ["S1", "H10", "C4"], 0)
    sample("sample_4_hands", [["C8", "D8", "H5"], ["S9", "C9", "D3"], ["H13", "S13"],
                              ["C2", "D2", "S5", "H4"]], ["S1", "H10", "C4", "D6", "S7"], 2)
    print(f"\nsample frames: {out}")


# ------------------------------------------------------------------ cli
def main():
    parser = argparse.ArgumentParser(description="measure the blackjack house edge")
    parser.add_argument("multipliers", nargs="*", type=float,
                        help=f"blackjack payouts to try (default: {SWEEP})")
    parser.add_argument("-n", "--rounds", default=300_000, type=float, help="rounds to measure (300k ~ 20s, 1M for ±0.11%)")
    parser.add_argument("--baseline", action="store_true",
                        help="also measure hit/stand/surrender without split and double")
    parser.add_argument("--frames", action="store_true", help="render sample hands into tools/out")
    args = parser.parse_args()

    global rendering
    module, rendering = load_game()
    BlackjackGame = module.BlackjackGame
    out = Path(__file__).resolve().parent / "out"
    out.mkdir(exist_ok=True)
    random.seed(0)

    rounds = int(args.rounds)
    multipliers = args.multipliers or SWEEP
    measured_at = multipliers[0]
    original = BlackjackGame.BLACKJACK_MULTIPLIER

    # a short run with the real renderer on, then switch it off: drawing 300k frames is pointless
    for _ in range(100):
        play_round(BlackjackGame)
    print("renderer smoke test: 100 rounds ok", flush=True)
    real_render, real_write = BlackjackGame.render_hands, BlackjackGame.write_image
    BlackjackGame.render_hands = lambda self, **kwargs: None
    BlackjackGame.write_image = staticmethod(lambda image: "")

    try:
        if args.baseline:
            print("measuring hit/stand/surrender (no split, no double) …", flush=True)
            random.seed(0)
            report("hit/stand/surrender (no split)", *simulate(BlackjackGame, rounds, False)[:3], rounds)

        print(f"measuring {rounds:,} rounds with blackjack at X{measured_at:g} …", flush=True)
        BlackjackGame.BLACKJACK_MULTIPLIER = measured_at
        random.seed(0)
        edge, tally, hands, naturals = simulate(BlackjackGame, rounds)
        payout_curve(edge, naturals, rounds, measured_at, multipliers)
    finally:
        BlackjackGame.BLACKJACK_MULTIPLIER = original
        BlackjackGame.render_hands = real_render
        BlackjackGame.write_image = staticmethod(real_write)

    if args.frames:
        render_frames(module, out)


if __name__ == "__main__":
    main()
