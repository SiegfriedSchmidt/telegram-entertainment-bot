import random
from lib import database
from lib.gambling.base import BaseGame
from lib.gambling.blackjack_rendering import *
from lib.init import tmp_folder_path
from lib.ledger.ledger import Ledger
from lib.models import MONEY_TYPE, BlackjackResultType, StatsType
from lib.temporal_storage import UserProfile


class BlackjackGame(BaseGame):
    MIN_BET = 100

    def __init__(self, ledger: Ledger, user: UserProfile, user_bet: MONEY_TYPE = None):
        self.deck: list[str] = list(cards.keys())
        random.shuffle(self.deck)
        self.dealer_hand: list[str] = []
        self.player_hand: list[str] = []

        super().__init__(ledger, user, user_bet if user_bet else user.blackjack_bet)

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
        self.finish_game("Blackjack", multiplier)
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
