"""Tresette with Italian cards: 2v2 (partners sit opposite, 10 cards each) and 1v1 (tresette a
due: 10 cards each, the other 20 form a talon; after each trick the winner draws first, then the
other, and both drawn cards are shown to everyone).

No trumps: you must follow the suit led if you can, and the highest card of that suit wins.
Strength: 3, 2, asso, re, cavallo, fante, 7, 6, 5, 4. Points: the asso is worth 1, a 2, 3 or
figure 1/3, the last trick 1 more: 11 and 2/3 per hand, so everything is counted in thirds (35 per
hand) and a side keeps floor(thirds / 3) points. Accusi (optional, on by default) are declared
automatically at each player's first play: three or four 3s, 2s or assi (3 or 4 points) and the
napoletana, 3-2-asso of one suit (3 points). Hands follow one another until a side reaches the
target (11, 21 or 31; 21 by default), or a single hand with option ``hands=1``.
"""

from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode, team_winners
from marione.games.cards import IT_SUITS, italian_deck, shuffled, suit

STRENGTH = "4567FCR123"  # weakest to strongest
THIRDS = {"1": 3, "2": 1, "3": 1, "F": 1, "C": 1, "R": 1}
HAND_THIRDS = 35  # 11 points and 2/3 in cards plus the last trick
TARGETS = (11, 21, 31)


def strength(card: str) -> int:
    return STRENGTH.index(card[0])


def thirds(card: str) -> int:
    return THIRDS.get(card[0], 0)


def is_liscio(card: str) -> bool:
    return card[0] in "4567"


def find_accusi(hand: list[str]) -> list[dict[str, Any]]:
    """The accusi in a hand: tris/poker of 3, 2 or asso, and napoletane (3-2-asso of a suit)."""
    found: list[dict[str, Any]] = []
    for r in "321":
        cards = [c for c in hand if c[0] == r]
        if len(cards) >= 3:
            kind = "poker" if len(cards) == 4 else "tris"
            found.append({"kind": kind, "cards": sorted(cards), "points": len(cards)})
    for s in IT_SUITS:
        if all(r + s in hand for r in "321"):
            found.append({"kind": "napoletana", "cards": [r + s for r in "321"], "points": 3})
    return found


class Tresette(Game):
    key: ClassVar[str] = "tresette"
    modes: ClassVar[tuple[Mode, ...]] = (
        Mode("2v2", 4, teams=((0, 2), (1, 3))),
        Mode("1v1", 2),
    )

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        target = int(self.options.get("target", 21))
        self.target = target if target in TARGETS else 21
        self.single = int(self.options.get("hands", 0)) == 1
        self.with_accusi = bool(self.options.get("accusi", True))
        self.sides = len(mode.teams) if mode.teams else mode.seats
        self.scores = [0] * self.sides
        self.hand_no = 0
        self.last_hand: dict[str, Any] | None = None
        self.done = False
        self.last_trick: list[tuple[int, str]] = []
        self.last_winner: int | None = None
        self._deal()

    # --- dealing -----------------------------------------------------------------------------

    def _deal(self) -> None:
        deck = shuffled(italian_deck(), self.rng)
        self.hands: list[list[str]] = [deck[i * 10 : (i + 1) * 10] for i in range(self.seats)]
        self.talon: list[str] = deck[self.seats * 10 :]
        self.drawn: list[tuple[int, str]] = []
        self.trick: list[tuple[int, str]] = []
        self.played: set[str] = set()
        self.hand_thirds = [0] * self.sides
        self.card_thirds = [0] * self.sides
        self.accusi: list[dict[str, Any]] = []
        self.declared: set[int] = set()
        self.turn = self.hand_no % self.seats
        self.log.add("deal", hand=self.hand_no + 1, leader=self.turn)

    def side_of(self, seat: int) -> int:
        return self.mode.team_of(seat)

    # --- rules -------------------------------------------------------------------------------

    @property
    def lead_suit(self) -> str | None:
        return suit(self.trick[0][1]) if self.trick else None

    def playable(self, seat: int) -> list[str]:
        hand = self.hands[seat]
        lead = self.lead_suit
        if lead is not None:
            same = [c for c in hand if suit(c) == lead]
            if same:
                return same
        return list(hand)

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
            raise IllegalMove("you must follow suit")
        if self.with_accusi and seat not in self.declared:
            self._declare(seat)
        self.declared.add(seat)
        self.hands[seat].remove(card)
        self.played.add(card)
        self.trick.append((seat, card))
        self.log.add("play", seat=seat, card=card)
        if len(self.trick) < self.seats:
            self.turn = (seat + 1) % self.seats
            return
        self._close_trick()

    def _declare(self, seat: int) -> None:
        for acc in find_accusi(self.hands[seat]):
            entry = {"seat": seat, **acc}
            self.accusi.append(entry)
            self.hand_thirds[self.side_of(seat)] += 3 * acc["points"]
            self.log.add(
                "accuso", seat=seat, accuso=acc["kind"], cards=acc["cards"], points=acc["points"]
            )

    def _trick_winner(self) -> int:
        lead = suit(self.trick[0][1])
        best_seat, best = self.trick[0]
        for s, c in self.trick[1:]:
            if suit(c) == lead and strength(c) > strength(best):
                best_seat, best = s, c
        return best_seat

    def _close_trick(self) -> None:
        winner = self._trick_winner()
        side = self.side_of(winner)
        got = sum(thirds(c) for _, c in self.trick)
        last = not any(self.hands) and not self.talon
        if last:
            got += 3
        self.card_thirds[side] += got
        self.hand_thirds[side] += got
        self.last_trick, self.last_winner = self.trick, winner
        self.trick = []
        self.log.add("trick", seat=winner, thirds=got, last=last)
        if self.talon:
            self.drawn = []
            for i in range(self.seats):
                s = (winner + i) % self.seats
                c = self.talon.pop()
                self.hands[s].append(c)
                self.drawn.append((s, c))
            self.log.add("draw", cards=[{"seat": s, "card": c} for s, c in self.drawn])
        else:
            self.drawn = []
        self.turn = winner
        if last:
            self._end_hand()

    def _end_hand(self) -> None:
        gained = [t // 3 for t in self.hand_thirds]
        for i, g in enumerate(gained):
            self.scores[i] += g
        self.last_hand = {
            "thirds": list(self.hand_thirds),
            "cardThirds": list(self.card_thirds),
            "points": gained,
            "accusi": list(self.accusi),
        }
        self.log.add("hand", hand=self.hand_no + 1, points=gained, scores=list(self.scores))
        self.hand_no += 1
        top = max(self.scores)
        if self.single or (top >= self.target and self.scores.count(top) == 1):
            self.done = True
            return
        self._deal()

    @property
    def finished(self) -> bool:
        return self.done

    # --- scoring -----------------------------------------------------------------------------

    def _winning_side(self) -> int | None:
        if not self.done:
            return None
        keys = [(self.scores[i], self.hand_thirds[i]) for i in range(self.sides)]
        top = max(keys)
        if keys.count(top) > 1:
            return None
        return keys.index(top)

    def winners(self) -> list[int]:
        return team_winners(self.mode, self._winning_side())

    def summary(self) -> dict[str, Any]:
        return {
            "scores": list(self.scores),
            "hands": self.hand_no,
            "lastHand": self.last_hand,
            "winners": self.winners(),
        }

    # --- the computer player -----------------------------------------------------------------

    def _is_master(self, card: str, seat: int) -> bool:
        """No stronger card of its suit is still out of sight for `seat`."""
        for r in STRENGTH[strength(card) + 1 :]:
            c = r + suit(card)
            if c not in self.played and c not in self.hands[seat]:
                return False
        return True

    def _dump(self, cards: list[str]) -> str:
        return min(cards, key=lambda c: (thirds(c), not is_liscio(c), strength(c)))

    def bot_action(self, seat: int) -> Action:
        cards = self.playable(seat)
        return {"type": "play", "card": self._choose(seat, cards)}

    def _choose(self, seat: int, cards: list[str]) -> str:
        hand = self.hands[seat]
        if not self.trick:
            masters = [c for c in cards if self._is_master(c, seat) and thirds(c) > 0]
            if masters:
                return max(masters, key=lambda c: (thirds(c), strength(c)))
            lisci = [c for c in cards if is_liscio(c)]
            if lisci:
                # From the longest suit, to run the others out of it.
                return max(
                    lisci, key=lambda c: (sum(suit(x) == suit(c) for x in hand), -strength(c))
                )
            return self._dump(cards)
        lead = suit(self.trick[0][1])
        win_seat = self._trick_winner()
        best = next(c for s, c in self.trick if s == win_seat)
        on_table = sum(thirds(c) for _, c in self.trick)
        last_to_play = len(self.trick) == self.seats - 1
        following = suit(cards[0]) == lead
        partner_winning = bool(self.mode.teams) and self.side_of(win_seat) == self.side_of(seat)
        if partner_winning and (last_to_play or self._is_master(best, seat)):
            # Load the partner's trick with points, keeping 3s and 2s that may win later.
            gifts = [c for c in cards if c[0] not in "32"] or cards
            return max(gifts, key=lambda c: (thirds(c), -strength(c)))
        if following:
            winning = [c for c in cards if strength(c) > strength(best)]
            if winning:
                cheapest = min(winning, key=strength)
                if last_to_play and (on_table > 0 or thirds(cheapest) > 0):
                    return cheapest
                masters = [c for c in winning if self._is_master(c, seat)]
                if masters and (on_table > 0 or len(self.trick) == 1):
                    return min(masters, key=strength)
                if last_to_play:
                    return cheapest
        return self._dump(cards)

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        return {
            "hand": list(self.hands[seat]) if seat is not None else [],
            "handCounts": [len(h) for h in self.hands],
            "trick": [{"seat": s, "card": c} for s, c in self.trick],
            "lastTrick": [{"seat": s, "card": c} for s, c in self.last_trick],
            "lastWinner": self.last_winner,
            "talon": len(self.talon) if self.seats == 2 else None,
            "drawn": [{"seat": s, "card": c} for s, c in self.drawn],
            "scores": list(self.scores),
            "handPoints": {
                "thirds": list(self.hand_thirds),
                "points": [t // 3 for t in self.hand_thirds],
            },
            "accusi": [dict(a) for a in self.accusi],
            "turn": None if self.finished else self.turn,
            "leadSuit": self.lead_suit,
            "handNo": self.hand_no + (0 if self.done else 1),
            "target": None if self.single else self.target,
            "lastHand": self.last_hand,
        }
