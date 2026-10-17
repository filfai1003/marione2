"""Texas Hold'em, fixed limit, 2 to 8 seats. One object is one hand.

Blinds are forced actions (``{"type": "blind"}``, its cost is the blind): the seat on the
button's left is asked for the small blind (max(1, unit // 2)), the next one for the big blind
(one unit). Heads-up the button posts the small blind. A seat asked for a blind may fold instead
and sits the hand out; the blind then moves on to the next seat. The big blind counts as the
first bet preflop and gets its option. Preflop and flop bet one unit, turn and river two.
Showdown with the best five of seven cards; ties split the pot.
"""

from collections import Counter
from typing import Any, ClassVar

from marione.games.base import Action, Mode
from marione.games.cards import fr_value, french_deck, shuffled, suit
from marione.games.poker_eval import (
    HIGH_CARD,
    PAIR,
    TWO_PAIR,
    LimitPoker,
    best_five,
    seat_modes,
)

STREETS = ("preflop", "flop", "turn", "river")


class Texas(LimitPoker):
    key: ClassVar[str] = "texas"
    modes: ClassVar[tuple[Mode, ...]] = seat_modes(2, 8)
    post_type: ClassVar[str] = "blind"
    post_phase: ClassVar[str] = "blinds"
    betting_phases: ClassVar[tuple[str, ...]] = STREETS

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        self.deck = shuffled(french_deck(), rng)
        self.board: list[str] = []
        self.small_blind = max(1, self.unit // 2)
        self.big_blind = self.unit
        first = self.button if mode.seats == 2 else (self.button + 1) % mode.seats
        self.post_queue = self.order_from(first)
        self.post_amounts = [self.small_blind, self.big_blind]

    def posts_are_bets(self) -> bool:
        return True

    def bet_size(self) -> int:
        return self.unit * 2 if self.phase in ("turn", "river") else self.unit

    def eval_cards(self, seat: int) -> list[str]:
        return self.hands[seat] + self.board

    def after_posting(self) -> None:
        for _ in range(2):
            for s in self.order_from((self.button + 1) % self.seats):
                if not self.folded[s]:
                    self.hands[s].append(self.deck.pop())
        self.phase = "preflop"
        self.raises = 1 if len(self.posted) >= 2 else 0
        last = self.posted[-1]
        self.pending = [s for s in self.order_from((last + 1) % self.seats) if not self.folded[s]]

    def round_over(self) -> None:
        i = STREETS.index(self.phase)
        if i == len(STREETS) - 1:
            self.do_showdown()
            return
        self.phase = STREETS[i + 1]
        dealt = [self.deck.pop() for _ in range(3 if self.phase == "flop" else 1)]
        self.board.extend(dealt)
        self.log.add("deal", street=self.phase, cards=dealt)
        self.start_round((self.button + 1) % self.seats)

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        if self.phase == self.post_phase:
            return self.bot_post(seat)
        hole = self.hands[seat]
        if self.phase == "preflop":
            strength = preflop_strength(hole)
        else:
            strength = postflop_strength(hole, self.board)
        return self.bot_bet(seat, strength)

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        v = self.base_view(seat)
        v["board"] = list(self.board)
        v["smallBlind"] = self.small_blind
        v["bigBlind"] = self.big_blind
        return v


def preflop_strength(hole: list[str]) -> float:
    """A rough chart: pairs, high cards, suited and connected hands."""
    a, b = sorted((fr_value(c) for c in hole), reverse=True)
    if a == b:
        return 0.5 + a / 28
    s = a / 14 * 0.45
    if suit(hole[0]) == suit(hole[1]):
        s += 0.06
    if a - b <= 2:
        s += 0.05
    if b >= 10:
        s += 0.15
    elif a == 14:
        s += 0.05
    return s


def postflop_strength(hole: list[str], board: list[str]) -> float:
    rank, _ = best_five(hole + board)
    cat = rank[0]
    board_cat = best_five(board)[0][0] if len(board) >= 5 else HIGH_CARD
    if len(board) < 5:
        board_values = Counter(fr_value(c) for c in board)
        if max(board_values.values()) >= 2:
            board_cat = PAIR
    if cat > TWO_PAIR and cat > board_cat:
        return min(1.0, 0.8 + cat * 0.025)
    if cat == TWO_PAIR and board_cat < PAIR:
        return 0.75
    hole_values = [fr_value(c) for c in hole]
    top = max(fr_value(c) for c in board)
    paired = [v for v in hole_values if any(fr_value(c) == v for c in board)]
    s = 0.15
    if hole_values[0] == hole_values[1] and hole_values[0] > top:
        s = 0.65  # an overpair
    elif paired:
        s = 0.6 if max(paired) == top else 0.45
    elif hole_values[0] == hole_values[1]:
        s = 0.4
    if len(board) < 5:
        suits = Counter(suit(c) for c in hole + board)
        if max(suits.values()) == 4:
            s = max(s, 0.42)
        values = sorted({fr_value(c) for c in hole + board} | ({1} if 14 in hole_values else set()))
        for lo in values:
            if sum(1 for v in values if lo <= v <= lo + 3) == 4:
                s = max(s, 0.4)
    return s
