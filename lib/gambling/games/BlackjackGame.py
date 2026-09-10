import random
from dataclasses import dataclass
from lib import database
from lib.gambling.base import BaseGame
from lib.gambling.blackjack_rendering import *
from lib.init import tmp_folder_path
from lib.ledger.ledger import Ledger
from lib.models import MONEY_TYPE, BlackjackResultType, StatsType
from lib.temporal_storage import UserProfile


@dataclass
class Hand:
    cards: list[str]
    raw_bet: int  # bet as the player sees it
    bet: int  # bet after fees, payouts are counted from it
    from_split: bool = False  # a hand made by a split is never a natural blackjack
    split_aces: bool = False  # split aces: no actions left after the extra card
    stood: bool = False
    result: BlackjackResultType | None = None

    @property
    def done(self) -> bool:
        return self.stood or self.result is not None


class BlackjackGame(BaseGame):
    MIN_BET = 100
    BLACKJACK_MULTIPLIER = 2.25  # a natural pays 5:4; 2.0 = even money, 2.5 = 3:2
    MAX_HANDS = 4  # resplit limit
    DOUBLE_AFTER_SPLIT = True  # doubling is allowed on hands made by a split
    SPLIT_ACES_ONE_CARD = True  # split aces get exactly one card and stand
    SURRENDER_FIRST_DECISION_ONLY = True  # late surrender

    def __init__(self, ledger: Ledger, user: UserProfile, user_bet: MONEY_TYPE = None):
        self.deck: list[str] = list(cards.keys())
        random.shuffle(self.deck)
        self.dealer_hand: list[str] = []
        self.hands: list[Hand] = []
        self.active: int = 0

        super().__init__(ledger, user, user_bet if user_bet else user.blackjack_bet)

    def play(self):
        pass

    def get_random_card(self) -> str:
        if not self.deck:  # four hands can theoretically eat all 52 cards
            self.deck = list(cards.keys())
            random.shuffle(self.deck)
        return self.deck.pop()

    @property
    def active_hand(self) -> Hand:
        return self.hands[self.active]

    @property
    def finished(self) -> bool:
        return all(hand.result is not None for hand in self.hands)

    # ------------------------------------------------------------------ actions
    def start(self) -> str:
        self.dealer_hand = [self.get_random_card(), self.get_random_card()]
        self.hands = [Hand(cards=[self.get_random_card(), self.get_random_card()],
                           raw_bet=self.user_bet, bet=self.gamble_bet)]
        return self.write_image(self.render_hands(active=0))

    def hit(self) -> tuple[str, bool]:
        hand = self.active_hand
        hand.cards.append(self.get_random_card())
        if calculate_score(hand.cards) > 21:
            hand.result = BlackjackResultType.bust
            self._next_hand()
        return self._render()

    def stand(self) -> tuple[str, bool]:
        self.active_hand.stood = True
        self._next_hand()
        return self._render()

    def double(self) -> tuple[str, bool]:
        """Twice the bet, exactly one more card, and the hand is done."""
        hand = self.active_hand
        hand.bet += self.add_bet(hand.raw_bet)
        hand.raw_bet *= 2
        hand.stood = True
        hand.cards.append(self.get_random_card())
        if calculate_score(hand.cards) > 21:
            hand.result = BlackjackResultType.bust
        self._next_hand()
        return self._render()

    def split(self) -> tuple[str, bool]:
        """Cut a pair into two hands, each one getting a fresh card."""
        hand = self.active_hand
        aces = card_value(hand.cards[0]) == 1
        card = hand.cards.pop()

        hand.from_split, hand.split_aces = True, aces
        new_hand = Hand(cards=[card], raw_bet=hand.raw_bet, bet=self.add_bet(hand.raw_bet),
                        from_split=True, split_aces=aces)
        self.hands.insert(self.active + 1, new_hand)

        for split_hand in (hand, new_hand):
            split_hand.cards.append(self.get_random_card())
            split_hand.stood = aces and self.SPLIT_ACES_ONE_CARD

        self._next_hand()
        return self._render()

    def surrender(self) -> tuple[str, bool]:
        self.active_hand.result = BlackjackResultType.surrender
        self._next_hand()
        return self._render()

    # -------------------------------------------------------------------- rules
    def get_available_actions(self) -> list[str]:
        if self.finished:
            return []

        hand = self.active_hand
        if self.SPLIT_ACES_ONE_CARD and hand.split_aces:
            return []

        actions = ["hit", "stand"]
        if self.can_double():
            actions.append("double")
        if self.can_split():
            actions.append("split")
        if self.can_surrender():
            actions.append("surrender")
        return actions

    def can_double(self) -> bool:
        hand = self.active_hand
        return (self._first_decision(hand)
                and (not hand.from_split or self.DOUBLE_AFTER_SPLIT)
                and self._can_raise(hand))

    def can_split(self) -> bool:
        hand = self.active_hand
        return (self._first_decision(hand)
                and not hand.split_aces
                and len(self.hands) < self.MAX_HANDS
                and card_value(hand.cards[0]) == card_value(hand.cards[1])
                and self._can_raise(hand))

    def can_surrender(self) -> bool:
        hand = self.active_hand
        if hand.from_split:  # no surrender on split hands
            return False
        return self._first_decision(hand) or not self.SURRENDER_FIRST_DECISION_ONLY

    @staticmethod
    def _first_decision(hand: Hand) -> bool:
        return len(hand.cards) == 2 and not hand.stood

    def _can_raise(self, hand: Hand) -> bool:
        """Is there free balance left to match the hand bet one more time?"""
        return self.ledger.get_user_balance(self.user.id) >= hand.raw_bet

    # ----------------------------------------------------------------- resolving
    def _next_hand(self) -> None:
        """Move to the next hand waiting for a decision, or let the dealer play."""
        self.active = next((i for i in range(self.active, len(self.hands)) if not self.hands[i].done),
                           len(self.hands))
        if self.active == len(self.hands):
            self._resolve_dealer()

    def _resolve_dealer(self) -> None:
        """The dealer plays once, after every player hand is settled."""
        pending = [hand for hand in self.hands if hand.result is None]
        if not pending:
            return

        dealer_blackjack = is_blackjack(self.dealer_hand)
        if not dealer_blackjack:
            while calculate_score(self.dealer_hand) < 17:
                self.dealer_hand.append(self.get_random_card())

        for hand in pending:
            hand.result = self._compare(hand, dealer_blackjack)

    def _compare(self, hand: Hand, dealer_blackjack: bool) -> BlackjackResultType:
        player_blackjack = not hand.from_split and is_blackjack(hand.cards)
        if player_blackjack or dealer_blackjack:
            if player_blackjack and dealer_blackjack:
                return BlackjackResultType.draw
            if player_blackjack:
                return BlackjackResultType.blackjack
            return BlackjackResultType.lose

        dealer_score = calculate_score(self.dealer_hand)
        player_score = calculate_score(hand.cards)
        if dealer_score > 21 or dealer_score < player_score:
            return BlackjackResultType.win
        elif dealer_score == player_score:
            return BlackjackResultType.draw
        else:
            return BlackjackResultType.lose

    # ----------------------------------------------------------------- rendering
    def _render(self) -> tuple[str, bool]:
        """Screenshot of the current state plus the flag "the round is over"."""
        finished = self.finished
        image = self.render_hands(dealer_open=finished, active=None if finished else self.active)
        return self.write_image(image), finished

    def get_active_hand_caption(self) -> str:
        return f"Hand {self.active + 1}/{len(self.hands)}. " if len(self.hands) > 1 else ""

    def render_hands(self, dealer_open: bool = False, active: int | None = None) -> np.ndarray:
        frame = table.copy()
        card_pad = card_size[0]
        start_pos = math.floor((table_w - card_pad * len(self.dealer_hand)) / 2)

        if start_pos < 0:
            card_pad = math.floor((table_w - card_size[0]) / (len(self.dealer_hand) - 1))
            start_pos = 0

        for j, card in enumerate(self.dealer_hand):
            target_pos = start_pos + card_pad * j, 100
            draw_card(frame, target_pos, card if j < len(self.dealer_hand) - 1 or dealer_open else None)

        hands_cards = [hand.cards for hand in self.hands]
        if len(hands_cards) == 1:
            for j, card in enumerate(hands_cards[0]):
                draw_card(frame, get_pos(j), card)
        else:
            positions, scale = get_hands_positions(hands_cards)
            for i, (hand_pos, hand_cards) in enumerate(zip(positions, hands_cards)):
                if i == active:
                    draw_hand_focus(frame, hand_pos, scale)
                for pos, card in zip(hand_pos, hand_cards):
                    draw_card(frame, pos, card, scale=scale)

        return frame

    @staticmethod
    def write_image(image: np.ndarray) -> str:
        filename = tmp_folder_path / f"blackjack_{random.randint(0, 1 << 31)}.png"
        cv2.imwrite(filename, image)
        return filename

    # -------------------------------------------------------------------- payout
    @staticmethod
    def _get_caption_and_multiplier(result: BlackjackResultType) -> tuple[str, float]:
        match result:
            case BlackjackResultType.blackjack:
                return "Blackjack", BlackjackGame.BLACKJACK_MULTIPLIER
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

    def get_caption_and_record_gain(self) -> str:
        parts, win_amount = [], 0
        for i, hand in enumerate(self.hands):
            caption, multiplier = self._get_caption_and_multiplier(hand.result)
            win_amount += multiplier * hand.bet
            parts.append(f"{caption} X{multiplier}" if len(self.hands) == 1
                         else f"{i + 1}) {caption} X{multiplier}")

        multiplier = round(win_amount / self.gamble_bet, 2)
        self.finish_game("Blackjack", multiplier, raw_win_amount=int(win_amount))
        database.update_user_stats(
            self.user.id,
            StatsType.blackjack_win if win_amount > self.gamble_bet else StatsType.blackjack_all
        )

        caption = " | ".join(parts)
        if len(self.hands) > 1:
            caption += f" → X{multiplier:g}"
        return f"{caption}! {self.get_balance_str()}"
