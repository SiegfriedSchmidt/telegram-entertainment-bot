import cv2
import numpy as np
import math
import random
from lib.init import blackjack_assets_folder_path, tmp_folder_path
from lib.ledger.ledger import Ledger
from lib.models import BlackjackResultType, StatsType
from lib import database
from lib.temporal_storage import UserProfile
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


class Blackjack:
    def __init__(self, ledger: Ledger, user: UserProfile, bet: str | int):
        self.deck: list[str] = list(cards.keys())
        random.shuffle(self.deck)

        self.dealer_hand: list[str] = []
        self.player_hand: list[str] = []
        self.ledger = ledger
        self.user = user
        self.bet = int(bet)
        self.process_bet()

    def process_bet(self):
        if self.bet < 100:
            raise RuntimeError("Bet should be more than 100!")
        self.ledger.record_deposit(self.user.id, self.bet, "Blackjack bet")

    def get_random_card(self) -> str:
        return self.deck.pop()

    @staticmethod
    def write_image(image: np.ndarray) -> str:
        filename = tmp_folder_path / f"blackjack_{random.randint(0, 1 << 31)}.png"
        cv2.imwrite(filename, image)
        return filename

    @staticmethod
    def _get_caption_and_multiplier(result: BlackjackResultType) -> tuple[str, float]:
        match result:
            case BlackjackResultType.win:
                return "You won", 2
            case BlackjackResultType.draw:
                return "It's a draw", 1
            case BlackjackResultType.surrender:
                return "You surrendered", 0.5
            case BlackjackResultType.lose:
                return "You lost", 0
            case BlackjackResultType.bust:
                return "You busted", 0

    def get_caption_and_record_gain(self, result: BlackjackResultType) -> str:
        caption, multiplier = self._get_caption_and_multiplier(result)
        gain = int(self.bet * multiplier)
        if gain:
            self.ledger.record_gain(self.user.id, gain, f"Blackjack gain X{multiplier}")

        database.update_user_stats(
            self.user.id,
            StatsType.blackjack_win if result == BlackjackResultType.win else StatsType.blackjack_all
        )
        return caption + f" X{multiplier}! {self.user}: {self.ledger.get_user_balance(self.user.id)}."

    def start(self) -> str:
        self.dealer_hand.append(self.get_random_card())
        self.dealer_hand.append(self.get_random_card())
        self.player_hand.append(self.get_random_card())
        self.player_hand.append(self.get_random_card())
        return self.write_image(self.render_hands())

    def hit(self) -> tuple[str, bool]:
        self.player_hand.append(self.get_random_card())
        score = calculate_score(self.player_hand)
        lose = score > 21

        filename = self.write_image(self.render_hands(dealer_open=lose))
        return filename, lose

    def surrender(self) -> str:
        filename = self.write_image(self.render_hands(dealer_open=True))
        return filename

    def stand(self) -> tuple[str, BlackjackResultType]:
        # check blackjacks
        player_blackjack = is_blackjack(self.player_hand)
        dealer_blackjack = is_blackjack(self.dealer_hand)
        if player_blackjack or dealer_blackjack:
            if player_blackjack and dealer_blackjack:
                result = BlackjackResultType.draw
            elif player_blackjack:
                result = BlackjackResultType.win
            else:
                result = BlackjackResultType.lose
            return self.write_image(self.render_hands(dealer_open=True)), result

        player_score = calculate_score(self.player_hand)
        dealer_score = calculate_score(self.dealer_hand)

        while dealer_score < 17:
            self.dealer_hand.append(self.get_random_card())
            dealer_score = calculate_score(self.dealer_hand)

        filename = self.write_image(self.render_hands(dealer_open=True))

        if dealer_score > 21 or dealer_score < player_score:
            return filename, BlackjackResultType.win
        elif dealer_score == player_score:
            return filename, BlackjackResultType.draw
        else:
            return filename, BlackjackResultType.lose

    def render_hands(self, dealer_open=False) -> np.ndarray:
        frame = table.copy()
        card_pad = card_size[0]
        start_pos = math.floor((table_w - card_pad * len(self.dealer_hand)) / 2)

        if start_pos < 0:
            card_pad = math.floor((table_w - card_size[0]) / (len(self.dealer_hand) - 1))
            start_pos = 0

        for j, card in enumerate(self.dealer_hand):
            target_pos = start_pos + card_pad * j, 100
            draw_card(frame, target_pos, card if j < len(self.dealer_hand) - 1 or dealer_open else None)

        for j, card in enumerate(self.player_hand):
            draw_card(frame, get_pos(j), card, 1)

        return frame


if __name__ == '__main__':
    ...
