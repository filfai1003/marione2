"""Briscola with Italian cards: 1v1, 1v1v1 (one 2 removed) and 2v2 (partners sit opposite).

Three cards each, the next card turned face up is the briscola (trump) and is the last card drawn.
A trick goes to the highest briscola played, otherwise to the highest card of the suit led.
Strength: asso, 3, re, cavallo, fante, 7, 6, 5, 4, 2. Points: asso 11, 3 10, re 4, cavallo 3,
fante 2 (120 in all). Whoever wins the trick draws first and leads the next one. More than half the
points wins; an even split is a draw.
"""

from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode, team_winners
from marione.games.cards import italian_deck, shuffled, suit

STRENGTH = "24567FCR31"  # weakest to strongest
POINTS = {"1": 11, "3": 10, "R": 4, "C": 3, "F": 2}


def points(card: str) -> int:
    return POINTS.get(card[0], 0)


def strength(card: str) -> int:
    return STRENGTH.index(card[0])


def beats(challenger: str, best: str, trump: str) -> bool:
    """Does `challenger` beat the card currently winning the trick?"""
    if suit(challenger) == suit(best):
        return strength(challenger) > strength(best)
    return suit(challenger) == trump


class Briscola(Game):
    key: ClassVar[str] = "briscola"
    modes: ClassVar[tuple[Mode, ...]] = (
        Mode("1v1", 2),
        Mode("1v1v1", 3),
        Mode("2v2", 4, teams=((0, 2), (1, 3))),
    )

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        deck = italian_deck()
        if mode.seats == 3:
            deck.remove("2b")  # 39 cards: 13 each
        self.deck = shuffled(deck, rng)
        self.hands: list[list[str]] = [[] for _ in range(mode.seats)]
        for _ in range(3):
            for s in range(mode.seats):
                self.hands[s].append(self.deck.pop())
        self.briscola = self.deck[0]  # face up under the deck: the last card drawn
        self.trump = suit(self.briscola)
        self.leader = 0
        self.turn = 0
        self.trick: list[tuple[int, str]] = []
        self.taken: list[list[str]] = [[] for _ in range(mode.seats)]
        self.last_trick: list[tuple[int, str]] = []
        self.last_winner: int | None = None

    # --- rules -------------------------------------------------------------------------------

    def to_act(self) -> list[int]:
        return [] if self.finished else [self.turn]

    def legal(self, seat: int) -> list[Action]:
        if seat != self.turn or self.finished:
            return []
        return [{"type": "play", "card": c} for c in self.hands[seat]]

    def act(self, seat: int, action: Action) -> None:
        card = action.get("card")
        if seat != self.turn or self.finished or action.get("type") != "play":
            raise IllegalMove("not your turn")
        if card not in self.hands[seat]:
            raise IllegalMove("card not in hand")
        self.hands[seat].remove(card)
        self.trick.append((seat, card))
        self.log.add("play", seat=seat, card=card)
        if len(self.trick) < self.seats:
            self.turn = (seat + 1) % self.seats
            return
        winner = self._trick_winner()
        self.taken[winner].extend(c for _, c in self.trick)
        self.last_trick, self.last_winner = self.trick, winner
        self.log.add("trick", seat=winner, points=sum(points(c) for _, c in self.trick))
        self.trick = []
        self._draw(winner)
        self.leader = self.turn = winner

    def _trick_winner(self) -> int:
        best_seat, best = self.trick[0]
        for s, c in self.trick[1:]:
            if beats(c, best, self.trump):
                best_seat, best = s, c
        return best_seat

    def _draw(self, first: int) -> None:
        if not self.deck:
            return
        for i in range(self.seats):
            s = (first + i) % self.seats
            if self.deck:
                self.hands[s].append(self.deck.pop())

    @property
    def finished(self) -> bool:
        return not self.trick and not any(self.hands) and not self.deck

    # --- scoring -----------------------------------------------------------------------------

    def side_points(self) -> list[int]:
        """Points per team (2v2) or per seat."""
        if self.mode.teams:
            return [sum(sum(points(c) for c in self.taken[s]) for s in t) for t in self.mode.teams]
        return [sum(points(c) for c in pile) for pile in self.taken]

    def winners(self) -> list[int]:
        if not self.finished:
            return []
        scores = self.side_points()
        top = max(scores)
        if scores.count(top) > 1:
            return []  # a draw: stakes back
        return team_winners(self.mode, scores.index(top))

    def summary(self) -> dict[str, Any]:
        return {"points": self.side_points(), "winners": self.winners()}

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        hand = self.hands[seat]
        if not self.trick:
            # Lead the least valuable card, keeping briscole for later.
            return {"type": "play", "card": min(hand, key=self._lead_cost)}
        best_seat, best = self.trick[0]
        for s, c in self.trick[1:]:
            if beats(c, best, self.trump):
                best_seat, best = s, c
        on_table = sum(points(c) for _, c in self.trick)
        partner_winning = bool(self.mode.teams) and self.mode.team_of(
            best_seat
        ) == self.mode.team_of(seat)
        if partner_winning:
            # Give the partner points, without wasting a briscola.
            safe = [c for c in hand if suit(c) != self.trump] or hand
            return {"type": "play", "card": max(safe, key=lambda c: (points(c), -strength(c)))}
        winning = [c for c in hand if beats(c, best, self.trump)]
        cheap_wins = [c for c in winning if suit(c) != self.trump]
        if cheap_wins:
            return {"type": "play", "card": max(cheap_wins, key=points)}
        if winning and on_table >= 10:
            return {"type": "play", "card": min(winning, key=lambda c: (points(c), strength(c)))}
        return {"type": "play", "card": min(hand, key=self._lead_cost)}

    def _lead_cost(self, card: str) -> tuple[int, int, int]:
        return (int(suit(card) == self.trump), points(card), strength(card))

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        return {
            "hand": list(self.hands[seat]) if seat is not None else [],
            "handCounts": [len(h) for h in self.hands],
            "briscola": self.briscola,
            "deck": len(self.deck),
            "trick": [{"seat": s, "card": c} for s, c in self.trick],
            "lastTrick": [{"seat": s, "card": c} for s, c in self.last_trick],
            "lastWinner": self.last_winner,
            "taken": [len(p) for p in self.taken],
            "turn": None if self.finished else self.turn,
            "points": self.side_points() if self.finished else None,
        }
