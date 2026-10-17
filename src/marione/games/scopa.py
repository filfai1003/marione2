"""Scopa with Italian cards: 1v1, 1v1v1 and 2v2 (partners sit opposite).

Four cards face up on the table (redealt if three or more re), three to each player per deal
until the deck ends. A card takes a table card of the same value (mandatory, and it must be a
single card if one exists), otherwise a set of table cards summing to its value; taking is
mandatory, and when several takes are possible the player chooses. Clearing the table is a
scopa (+1), except on the last play of a hand. At the end of a hand the cards left on the table
go to the last player who took. Points per hand: carte, denari, settebello, primiera (a tie in a
category gives nobody the point) plus scope. The match goes on, hand after hand, until a side
reaches the target (11 or 21) with a clear lead, or for a fixed number of hands (option "hands").
"""

from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode, team_winners
from marione.games.cards import it_number, italian_deck, shuffled, suit

PRIMIERA = {"7": 21, "6": 18, "1": 16, "5": 15, "4": 14, "3": 13, "2": 12}
CATEGORIES = ("carte", "denari", "settebello", "primiera")


def value(card: str) -> int:
    return it_number(card)


def primiera_value(card: str) -> int:
    return PRIMIERA.get(card[0], 10)


def primiera(cards: list[str]) -> int | None:
    """Sum of the best primiera card per suit; None without all four suits."""
    best: dict[str, int] = {}
    for c in cards:
        best[suit(c)] = max(best.get(suit(c), 0), primiera_value(c))
    if len(best) < 4:
        return None
    return sum(best.values())


def captures(card: str, table: list[str]) -> list[list[str]]:
    """Every take `card` may make from `table` (in table order); [] if it can only be laid."""
    v = value(card)
    same = [[c] for c in table if value(c) == v]
    if same:
        return same
    found: list[list[str]] = []

    def search(start: int, left: int, chosen: list[str]) -> None:
        if left == 0:
            found.append(list(chosen))
            return
        for i in range(start, len(table)):
            cv = value(table[i])
            if cv <= left:
                chosen.append(table[i])
                search(i + 1, left - cv, chosen)
                chosen.pop()

    search(0, v, [])
    return found


def unique_best(values: list[int | None]) -> int | None:
    """Index of the single highest value (ties and missing values give None)."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    top = max(present)
    if values.count(top) > 1:
        return None
    return values.index(top)


class Scopa(Game):
    key: ClassVar[str] = "scopa"
    modes: ClassVar[tuple[Mode, ...]] = (
        Mode("1v1", 2),
        Mode("1v1v1", 3),
        Mode("2v2", 4, teams=((0, 2), (1, 3))),
    )

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        self.target = 21 if int(self.options.get("target", 11)) == 21 else 11
        hands = self.options.get("hands")
        self.max_hands: int | None = max(1, int(hands)) if hands else None
        self.scores = [0] * self.sides
        self.hand_results: list[list[dict[str, int]]] = []
        self.hand_no = 0
        self.dealer = mode.seats - 1
        self.over = False
        self.deck: list[str] = []
        self.hands: list[list[str]] = []
        self.table: list[str] = []
        self.captured: list[list[str]] = []
        self.scope = [0] * self.sides
        self.turn = 0
        self.last_taker: int | None = None
        self.last_play: dict[str, Any] | None = None
        self._new_hand()

    @property
    def sides(self) -> int:
        return len(self.mode.teams) if self.mode.teams else self.mode.seats

    def side_of(self, seat: int) -> int:
        return self.mode.team_of(seat)

    # --- dealing -----------------------------------------------------------------------------

    def _new_hand(self) -> None:
        self.hand_no += 1
        self.dealer = (self.dealer + 1) % self.seats
        while True:
            self.deck = shuffled(italian_deck(), self.rng)
            self.table = [self.deck.pop() for _ in range(4)]
            if sum(c[0] == "R" for c in self.table) < 3:
                break
        self.hands = [[] for _ in range(self.seats)]
        self.captured = [[] for _ in range(self.seats)]
        self.scope = [0] * self.sides
        self.last_taker = None
        self.last_play = None
        self.turn = (self.dealer + 1) % self.seats
        self._deal()
        self.log.add("hand", number=self.hand_no, dealer=self.dealer)

    def _deal(self) -> None:
        for _ in range(3):
            for i in range(self.seats):
                self.hands[(self.dealer + 1 + i) % self.seats].append(self.deck.pop())

    # --- rules -------------------------------------------------------------------------------

    def to_act(self) -> list[int]:
        return [] if self.over else [self.turn]

    def legal(self, seat: int) -> list[Action]:
        if seat != self.turn or self.over:
            return []
        out: list[Action] = []
        for card in self.hands[seat]:
            takes = captures(card, self.table) or [[]]
            out.extend({"type": "play", "card": card, "take": t} for t in takes)
        return out

    def act(self, seat: int, action: Action) -> None:
        if seat != self.turn or self.over or action.get("type") != "play":
            raise IllegalMove("not your turn")
        card = action.get("card")
        if not isinstance(card, str) or card not in self.hands[seat]:
            raise IllegalMove("card not in hand")
        raw = action.get("take") or []
        if not isinstance(raw, list):
            raise IllegalMove("bad take")
        wanted = sorted(str(c) for c in raw)
        options = captures(card, self.table) or [[]]
        take = next((t for t in options if sorted(t) == wanted), None)
        if take is None:
            raise IllegalMove("take not allowed")
        self.hands[seat].remove(card)
        last = not self.deck and not any(self.hands)
        if take:
            for c in take:
                self.table.remove(c)
            self.captured[seat].extend([card, *take])
            self.last_taker = seat
            if not self.table and not last:
                self.scope[self.side_of(seat)] += 1
                self.log.add("scopa", seat=seat, card=card)
        else:
            self.table.append(card)
        self.log.add("play", seat=seat, card=card, take=list(take))
        self.last_play = {"seat": seat, "card": card, "take": list(take)}
        self.turn = (seat + 1) % self.seats
        if any(self.hands):
            return
        if self.deck:
            self._deal()
            return
        self._end_hand()

    def _end_hand(self) -> None:
        if self.last_taker is not None and self.table:
            self.captured[self.last_taker].extend(self.table)
            self.log.add("rest", seat=self.last_taker, cards=list(self.table))
            self.table = []
        result = self.hand_score()
        self.hand_results.append(result)
        for i, r in enumerate(result):
            self.scores[i] += r["total"]
        self.log.add("handEnd", totals=[r["total"] for r in result], scores=list(self.scores))
        if self._match_over():
            self.over = True
        else:
            self._new_hand()

    def _match_over(self) -> bool:
        if self.max_hands is not None:
            return self.hand_no >= self.max_hands
        top = max(self.scores)
        return top >= self.target and self.scores.count(top) == 1

    # --- scoring -----------------------------------------------------------------------------

    def side_cards(self) -> list[list[str]]:
        piles: list[list[str]] = [[] for _ in range(self.sides)]
        for s, pile in enumerate(self.captured):
            piles[self.side_of(s)].extend(pile)
        return piles

    def hand_score(self) -> list[dict[str, int]]:
        """The breakdown of the current hand per side (cards taken so far)."""
        piles = self.side_cards()
        winners = {
            "carte": unique_best([len(p) for p in piles]),
            "denari": unique_best([sum(suit(c) == "d" for c in p) for p in piles]),
            "settebello": next((i for i, p in enumerate(piles) if "7d" in p), None),
            "primiera": unique_best([primiera(p) for p in piles]),
        }
        out: list[dict[str, int]] = []
        for i in range(self.sides):
            row = {k: int(winners[k] == i) for k in CATEGORIES}
            row["scope"] = self.scope[i]
            row["total"] = sum(row.values())
            out.append(row)
        return out

    @property
    def finished(self) -> bool:
        return self.over

    def winners(self) -> list[int]:
        if not self.over:
            return []
        return team_winners(self.mode, unique_best(list(self.scores)))

    def summary(self) -> dict[str, Any]:
        return {
            "scores": list(self.scores),
            "hands": self.hand_results,
            "winners": self.winners(),
        }

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        moves = self.legal(seat)
        return max(moves, key=lambda a: self._rate(seat, a["card"], a["take"]))

    def _rate(self, seat: int, card: str, take: list[str]) -> float:
        last = not self.deck and sum(len(h) for h in self.hands) == 1
        score = 0.0
        if take:
            got = [card, *take]
            left = [c for c in self.table if c not in take]
            if not left and not last:
                score += 100
            score += 40 * ("7d" in got)
            score += 4 * sum(suit(c) == "d" for c in got)
            score += 2 * len(got)
            score += sum(primiera_value(c) - 12 for c in got if primiera_value(c) > 12) / 2
        else:
            left = [*self.table, card]
            score -= 40 * (card == "7d")
            score -= 3 * (suit(card) == "d")
            score -= max(0, primiera_value(card) - 12) / 2
            score -= value(card) / 10  # lay small cards: they make fewer sums
        if left and not last and sum(value(c) for c in left) <= 10:
            score -= 30
        return score

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        return {
            "hand": list(self.hands[seat]) if seat is not None else [],
            "handCounts": [len(h) for h in self.hands],
            "table": list(self.table),
            "deck": len(self.deck),
            "captured": [len(p) for p in self.captured],
            "scope": list(self.scope),
            "scores": list(self.scores),
            "lastPlay": dict(self.last_play) if self.last_play else None,
            "handResult": [dict(r) for r in self.hand_results[-1]] if self.hand_results else None,
            "turn": None if self.over else self.turn,
            "dealer": self.dealer,
            "handNo": self.hand_no,
            "target": self.target,
            "hands": self.max_hands,
        }
