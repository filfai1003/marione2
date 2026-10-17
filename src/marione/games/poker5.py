"""Five-card draw, fixed limit, 2 to 6 seats. One object is one hand.

Antes: every seat, from the button's left, is asked for an ante of one unit (``{"type":
"ante"}``) or may fold and sit the hand out. Five cards to each seat still in, a betting round
with the small bet (one unit) from the button's left, a draw (each seat discards 0..5 cards and
gets as many new ones; when the deck runs out the discards are shuffled into a new one), a
betting round with the big bet (two units), showdown.
"""

from collections import Counter
from typing import Any, ClassVar

from marione.games.base import Action, IllegalMove, Mode
from marione.games.cards import FR_RANKS, fr_value, french_deck, shuffled, suit
from marione.games.poker_eval import (
    FLUSH,
    FOUR,
    FULL_HOUSE,
    PAIR,
    STRAIGHT,
    THREE,
    TWO_PAIR,
    LimitPoker,
    evaluate5,
    seat_modes,
)

# Strength of a made five-card hand for the bot, by category.
CATEGORY_STRENGTH = (0.08, 0.45, 0.7, 0.8, 0.88, 0.9, 0.95, 0.98, 1.0)


class Poker5(LimitPoker):
    key: ClassVar[str] = "poker5"
    modes: ClassVar[tuple[Mode, ...]] = seat_modes(2, 6)
    post_type: ClassVar[str] = "ante"
    post_phase: ClassVar[str] = "ante"
    betting_phases: ClassVar[tuple[str, ...]] = ("bet1", "bet2")

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        self.deck = shuffled(french_deck(), rng)
        self.muck: list[str] = []
        self.drew: list[int | None] = [None] * mode.seats
        self.post_queue = self.order_from((self.button + 1) % mode.seats)
        self.post_amounts = [self.unit] * mode.seats

    # --- streets -----------------------------------------------------------------------------

    def bet_size(self) -> int:
        return self.unit * 2 if self.phase == "bet2" else self.unit

    def after_posting(self) -> None:
        for _ in range(5):
            for s in self.order_from((self.button + 1) % self.seats):
                if not self.folded[s]:
                    self.hands[s].append(self._draw_card())
        self.phase = "bet1"
        self.start_round((self.button + 1) % self.seats)

    def round_over(self) -> None:
        if self.phase == "bet1":
            self.phase = "draw"
            self.bets = [0] * self.seats
            self.current_bet = 0
            self.raises = 0
            first = (self.button + 1) % self.seats
            self.pending = [s for s in self.order_from(first) if not self.folded[s]]
        elif self.phase == "draw":
            self.phase = "bet2"
            self.start_round((self.button + 1) % self.seats)
        else:
            self.do_showdown()

    def _draw_card(self) -> str:
        if not self.deck:
            self.deck = shuffled(self.muck, self.rng)
            self.muck = []
        return self.deck.pop()

    # --- the draw ----------------------------------------------------------------------------

    def other_legal(self, seat: int) -> list[Action]:
        return [{"type": "draw", "min": 0, "max": 5}] if self.phase == "draw" else []

    def other_act(self, seat: int, action: Action) -> None:
        discard = action.get("discard", [])
        if action.get("type") != "draw" or self.phase != "draw":
            raise IllegalMove("bad action")
        if not isinstance(discard, list) or len(discard) > 5:
            raise IllegalMove("bad discard")
        hand = self.hands[seat]
        if len(set(discard)) != len(discard) or any(c not in hand for c in discard):
            raise IllegalMove("card not in hand")
        self.pending.pop(0)
        for c in discard:
            hand.remove(c)
        for _ in discard:
            hand.append(self._draw_card())
        self.muck.extend(discard)
        self.drew[seat] = len(discard)
        self.log.add("draw", seat=seat, count=len(discard))
        if not self.pending:
            self.round_over()

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        if self.phase == "ante":
            return self.bot_post(seat)
        hand = self.hands[seat]
        if self.phase == "draw":
            return {"type": "draw", "discard": bot_discard(hand)}
        strength = hand_strength(hand)
        if self.phase == "bet1":
            keep = 5 - len(bot_discard(hand))
            if keep == 4 and evaluate5(hand)[0] == 0:
                strength = max(strength, 0.3)  # a four-card draw is worth a call
        return self.bot_bet(seat, strength)

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        v = self.base_view(seat)
        v["drew"] = list(self.drew)
        v["deck"] = len(self.deck)
        v["ante"] = self.unit
        return v


def hand_strength(hand: list[str]) -> float:
    rank = evaluate5(hand)
    base = CATEGORY_STRENGTH[rank[0]]
    if rank[0] == PAIR:
        base += (rank[1][0] - 2) / 12 * 0.2  # high pairs are worth more
    elif rank[0] == 0:
        base += (rank[1][0] - 2) / 12 * 0.1
    return min(base, 1.0)


def bot_discard(hand: list[str]) -> list[str]:
    """Keep made hands and four-card draws; otherwise keep the two highest cards."""
    cat, _ = evaluate5(hand)
    if cat in (STRAIGHT, FLUSH, FULL_HOUSE) or cat > FOUR:
        return []
    counts = Counter(c[0] for c in hand)
    if cat in (PAIR, TWO_PAIR, THREE, FOUR):
        return [c for c in hand if counts[c[0]] == 1]
    suits = Counter(suit(c) for c in hand)
    s, n = suits.most_common(1)[0]
    if n == 4:
        return [c for c in hand if suit(c) != s]
    for drop in hand:
        rest = sorted(fr_value(c) for c in hand if c != drop)
        if rest[-1] - rest[0] == 3 and len(set(rest)) == 4:
            return [drop]
    keep = sorted(hand, key=lambda c: FR_RANKS.index(c[0]), reverse=True)[:2]
    return [c for c in hand if c not in keep]
