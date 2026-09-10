import cv2
import numpy as np
import math
from lib.init import blackjack_assets_folder_path
from lib.utils.cv2_utils import cv2_paste_with_alpha

table = cv2.imread(blackjack_assets_folder_path / "background.png", cv2.IMREAD_UNCHANGED)

table_w, table_h = table.shape[1], table.shape[0]
table_c = table_w // 2, table_h // 2

cards: dict[str, np.ndarray] = {}
for suit in ["C", "D", "H", "S"]:
    for idx in range(1, 14):
        card_id = f"{suit}{idx}"
        card_ = cv2.imread(blackjack_assets_folder_path / f"cards/{card_id}.png", cv2.IMREAD_UNCHANGED)
        cards[card_id] = cv2.resize(card_, (card_.shape[1] * 3, card_.shape[0] * 3))

card_back = cv2.imread(blackjack_assets_folder_path / "cards/1.png", cv2.IMREAD_UNCHANGED)
card_back = cv2.resize(card_back, (card_back.shape[1] * 3, card_back.shape[0] * 3))
card_size = card_back.shape[1], card_back.shape[0]

# split hands are placed side by side, each one fanned to the right
HAND_PAD = 10                  # minimal gap between two hands
HAND_STEP = 0.35               # share of a card width the next card of a hand is offset by
HAND_Y = 400                   # top of the player's row
FOCUS_COLOR = (60, 200, 255)   # BGR, glow around the hand being played
FOCUS_ALPHA = 0.35


def draw_card(frame: np.ndarray, target_pos: tuple[int, int], card: str | None = None,
              progress: float = 1.0, scale: float = 1.0):
    if card is None:
        card_front = card_back
    else:
        card_front = cards[card]

    flip_prog = max(0.0, min(1.0, progress))
    width_scale = max(0.05, abs(1 - 2 * flip_prog))  # 1 → 0 → 1

    cur_w = max(1, int(card_size[0] * scale * width_scale))
    cur_h = max(1, int(card_size[1] * scale))
    cur_card = card_back if flip_prog < 0.5 else card_front

    resized = cv2.resize(cur_card, (cur_w, cur_h), interpolation=cv2.INTER_NEAREST)

    x = target_pos[0] + (int(card_size[0] * scale) - cur_w) // 2
    y = target_pos[1]
    cv2_paste_with_alpha(frame, resized, (x, y))


def get_hands_positions(hands: list[list[str]]) -> tuple[list[list[tuple[int, int]]], float]:
    """Spread several hands over the table: card positions for every hand plus their scale."""
    slot_w = table_w // len(hands)
    max_cards = max(len(hand) for hand in hands)
    scale = min(1.0, (slot_w - HAND_PAD * 2) / (card_size[0] * (1 + HAND_STEP * (max_cards - 1))))

    step = int(card_size[0] * HAND_STEP * scale)
    card_w = int(card_size[0] * scale)

    positions = []
    for i, hand in enumerate(hands):
        x = i * slot_w + max(HAND_PAD, (slot_w - card_w - step * (len(hand) - 1)) // 2)
        positions.append([(x + step * j, HAND_Y) for j in range(len(hand))])

    return positions, scale


def draw_hand_focus(frame: np.ndarray, positions: list[tuple[int, int]], scale: float) -> None:
    """Highlight the hand the player is acting on."""
    pad = int(12 * scale)
    x0, y0 = positions[0][0] - pad, positions[0][1] - pad
    x1 = positions[-1][0] + int(card_size[0] * scale) + pad
    y1 = positions[0][1] + int(card_size[1] * scale) + pad

    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x1, y1), FOCUS_COLOR, -1)
    cv2.addWeighted(overlay, FOCUS_ALPHA, frame, 1 - FOCUS_ALPHA, 0, frame)


def get_pos(number: int):
    border_pad = 10
    start_height = 400
    card_pad_h = math.floor(((table_h - start_height) - border_pad - card_size[1]) / 11)
    card_pad_w = math.floor((table_w - border_pad * 2 - card_size[0]) / 11)
    return border_pad + number * card_pad_w, start_height + number * card_pad_h


def get_anim_pos(start: tuple[int, int], end: tuple[int, int], progress: float) -> tuple[int, int]:
    progress = max(0.0, min(1.0, progress))
    rel = end[0] - start[0], end[1] - start[1]
    return math.floor(start[0] + rel[0] * progress), math.floor(start[1] + rel[1] * progress)


def card_value(card: str) -> int:
    return min(10, int(card[1:]))


def calculate_score(hand: list[str]) -> int:
    score = 0
    ace_count = 0
    for card in hand:
        val = card_value(card)
        if val == 1:
            ace_count += 1
        score += val

    for i in range(ace_count):
        if score + 10 <= 21:
            score += 10

    return score


def is_blackjack(hand: list[str]) -> bool:
    first_two = {int(hand[0][1:]), int(hand[1][1:])}
    return 1 in first_two and any(el in first_two for el in [10, 11, 12, 13])


if __name__ == '__main__':
    ...
