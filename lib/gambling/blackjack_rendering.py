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


def draw_card(frame: np.ndarray, target_pos: tuple[int, int], card: str | None = None, progress: float = 1.0):
    if card is None:
        card_front = card_back
    else:
        card_front = cards[card]

    flip_prog = max(0.0, min(1.0, progress))
    scale = abs(1 - 2 * flip_prog)  # 1 → 0 → 1
    if scale < 0.05:
        scale = 0.05

    cur_w = int(card_size[0] * scale)
    cur_card = card_back if flip_prog < 0.5 else card_front

    resized = cv2.resize(cur_card, (cur_w, card_size[1]), interpolation=cv2.INTER_NEAREST)

    x = target_pos[0] + (card_size[0] - cur_w) // 2
    y = target_pos[1]
    cv2_paste_with_alpha(frame, resized, (x, y))


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


def calculate_score(hand: list[str]) -> int:
    score = 0
    ace_count = 0
    for card in hand:
        val = min(10, int(card[1:]))
        if val == 1:
            ace_count += 1
        score += val

    for i in range(ace_count):
        if score + 10 <= 21:
            score += 10

    return score


def is_blackjack(hand: list[str]) -> bool:
    first_two = {int(hand[0][1:]), int(hand[1][1:])}
    return 1 in first_two and any(el in first_two for el in [11, 12, 13])


if __name__ == '__main__':
    ...
