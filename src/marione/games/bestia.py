"""Bestia with Italian cards, for 3, 4 or 5 players: three cards each, the next card turned up gives
the trump suit. Three tricks; each trick earns a third of the pot, and whoever takes none is the
"bestia".

You must follow the suit led; if you cannot, you must trump if you can. With option ``strict``
(on by default) you must also head the trick: beat the winning card when you can (a higher card of
the suit led, or a higher trump once someone has trumped). Strength in a suit: asso, re, cavallo,
fante, 7, 6, 5, 4, 3, 2. The highest trump wins the trick, otherwise the highest card of the suit
led; the winner leads the next trick.
"""

from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode
from marione.games.cards import italian_deck, shuffled, suit

STRENGTH = "234567FCR1"  # weakest to strongest
TRICKS = 3


def strength(card: str) -> int:
    return STRENGTH.index(card[0])


def beats(challenger: str, best: str, trump: str) -> bool:
    """Does `challenger` beat the card currently winning the trick?"""
    if suit(challenger) == suit(best):
        return strength(challenger) > strength(best)
    return suit(challenger) == trump


class Bestia(Game):
    key: ClassVar[str] = "bestia"
    modes: ClassVar[tuple[Mode, ...]] = (Mode("3p", 3), Mode("4p", 4), Mode("5p", 5))

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        self.strict = bool(self.options.get("strict", True))
        deck = shuffled(italian_deck(), rng)
        self.hands: list[list[str]] = [[] for _ in range(mode.seats)]
        for _ in range(TRICKS):
            for s in range(mode.seats):
                self.hands[s].append(deck.pop())
        self.trump_card = deck.pop()
        self.trump = suit(self.trump_card)
        self.turn = 0
        self.trick: list[tuple[int, str]] = []
        self.tricks = [0] * mode.seats
        self.last_trick: list[tuple[int, str]] = []
        self.last_winner: int | None = None
        self.log.add("deal", trump=self.trump_card)

    # --- rules -------------------------------------------------------------------------------

    def _best(self) -> tuple[int, str]:
        best_seat, best = self.trick[0]
        for s, c in self.trick[1:]:
            if beats(c, best, self.trump):
                best_seat, best = s, c
        return best_seat, best

    def playable(self, seat: int) -> list[str]:
        hand = self.hands[seat]
        if not self.trick:
            return list(hand)
        lead = suit(self.trick[0][1])
        _, best = self._best()
        options = [c for c in hand if suit(c) == lead]
        if not options:
            options = [c for c in hand if suit(c) == self.trump]
        if not options:
            return list(hand)
        if self.strict:
            winning = [c for c in options if beats(c, best, self.trump)]
            if winning:
                return winning
        return options

    def to_act(self) -> list[int]:
        return [] if self.finished else [self.turn]

    def legal(self, seat: int) -> list[Action]:
        if seat != self.turn or self.finished:
            return []
        return [{"type": "play", "card": c} for c in self.playable(seat)]

    def act(self, seat: int, action: Action) -> None:
        if seat != self.turn or self.finished or action.get("type") != "play":
            raise IllegalMove("not your turn")
        card = action.get("card")
        if not isinstance(card, str) or card not in self.hands[seat]:
            raise IllegalMove("card not in hand")
        if card not in self.playable(seat):
            raise IllegalMove("follow suit, trump or beat the trick when you can")
        self.hands[seat].remove(card)
        self.trick.append((seat, card))
        self.log.add("play", seat=seat, card=card)
        if len(self.trick) < self.seats:
            self.turn = (seat + 1) % self.seats
            return
        winner, _ = self._best()
        self.tricks[winner] += 1
        self.last_trick, self.last_winner = self.trick, winner
        self.trick = []
        self.turn = winner
        self.log.add("trick", seat=winner)
        if self.finished:
            self.log.add("bestia", seats=self.bestia())

    @property
    def finished(self) -> bool:
        return sum(self.tricks) == TRICKS

    # --- scoring -----------------------------------------------------------------------------

    def bestia(self) -> list[int]:
        """Seats that took no trick (only once the round is over)."""
        if not self.finished:
            return []
        return [s for s, n in enumerate(self.tricks) if n == 0]

    def split(self) -> dict[int, int]:
        if not self.finished:
            return {}
        return {s: n for s, n in enumerate(self.tricks) if n > 0}

    def winners(self) -> list[int]:
        return sorted(self.split())

    def summary(self) -> dict[str, Any]:
        return {
            "tricks": list(self.tricks),
            "bestia": self.bestia(),
            "trump": self.trump_card,
            "winners": self.winners(),
        }

    # --- the computer player -----------------------------------------------------------------

    def _cost(self, card: str) -> tuple[int, int]:
        return (int(suit(card) == self.trump), strength(card))

    def bot_action(self, seat: int) -> Action:
        cards = self.playable(seat)
        if not self.trick:
            # Lead the strongest card: the surest way to a trick.
            return {"type": "play", "card": max(cards, key=lambda c: (strength(c), self._cost(c)))}
        _, best = self._best()
        winning = [c for c in cards if beats(c, best, self.trump)]
        pool = winning or cards
        return {"type": "play", "card": min(pool, key=self._cost)}

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        return {
            "hand": list(self.hands[seat]) if seat is not None else [],
            "handCounts": [len(h) for h in self.hands],
            "trump": self.trump_card,
            "trick": [{"seat": s, "card": c} for s, c in self.trick],
            "lastTrick": [{"seat": s, "card": c} for s, c in self.last_trick],
            "lastWinner": self.last_winner,
            "tricks": list(self.tricks),
            "turn": None if self.finished else self.turn,
            "leadSuit": suit(self.trick[0][1]) if self.trick else None,
            "bestia": self.bestia(),
        }
