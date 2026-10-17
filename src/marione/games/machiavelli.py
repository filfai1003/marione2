"""Machiavelli: rummy where the whole table belongs to everyone. Two French decks, no jokers,
2 to 5 players, 13 cards each, the rest is the stock.

On your turn you may play any number of cards from your hand and freely rearrange every meld on
the table, as long as at the end each group on the table is a valid meld (a set of 3-4 different
suits or a run of 3+ of a suit, ace low or high, no wrap; see `melds.py`) and every card that was
on the table is still there. A play sends the complete new table. If you play nothing you draw one
card (with an empty stock that is a pass). Whoever empties the hand wins; if the stock is empty and
a full round goes by with nobody playing, the fewest cards wins (then the lowest points; a further
tie splits the pot).
"""

import time
from collections import Counter
from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode
from marione.games.cards import FR_RANKS, french_deck, shuffled
from marione.games.melds import analyse, best_partition, card_points, find_melds, valid_card

HAND = 13
SEARCH_NODES = 800  # per hand card the bot tries to fit by rebuilding the table
SEARCH_SECONDS = 0.5  # per bot move


def _size(meld: Any) -> int:
    return len(meld)


class Machiavelli(Game):
    key: ClassVar[str] = "machiavelli"
    economy = "stake"
    modes: ClassVar[tuple[Mode, ...]] = tuple(Mode(f"{n}p", n) for n in range(2, 6))

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        self.stock = shuffled(french_deck(copies=2), rng)
        self.hands: list[list[str]] = [[] for _ in range(mode.seats)]
        for _ in range(HAND):
            for s in range(mode.seats):
                self.hands[s].append(self.stock.pop())
        self.table: list[list[str]] = []
        self.turn = 0
        self.passes = 0  # consecutive turns without a play while the stock is empty
        self.ended = False
        self.result: list[int] = []
        self.reason: str | None = None

    # --- rules -------------------------------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.ended

    def to_act(self) -> list[int]:
        return [] if self.ended else [self.turn]

    def legal(self, seat: int) -> list[Action]:
        if self.ended or seat != self.turn:
            return []
        return [{"type": "draw"}, {"type": "play"}]

    def act(self, seat: int, action: Action) -> None:
        if self.ended or seat != self.turn:
            raise IllegalMove("not your turn")
        kind = action.get("type")
        if kind == "draw":
            self._draw(seat)
        elif kind == "play":
            self._play(seat, action.get("table"))
        else:
            raise IllegalMove("unknown action")

    def _draw(self, seat: int) -> None:
        if self.stock:
            self.hands[seat].append(self.stock.pop())
            self.passes = 0
            self.log.add("draw", seat=seat)
        else:
            self.passes += 1
            self.log.add("pass", seat=seat)
            if self.passes >= self.seats:
                self._end_blocked()
                return
        self._next()

    def check_play(self, seat: int, table: object) -> tuple[list[list[str]], Counter[str]]:
        """Validate a complete new table: (the normalised groups, the cards from the hand)."""
        if not isinstance(table, list) or not all(isinstance(g, list) for g in table):
            raise IllegalMove("the table must be a list of groups")
        groups: list[list[str]] = []
        for g in table:
            if not all(valid_card(c) for c in g):
                raise IllegalMove("bad card")
            meld = analyse(g, jokers=False)
            if meld is None:
                raise IllegalMove(f"not a valid meld: {g}")
            groups.append(list(meld.cards))
        new = Counter(c for g in groups for c in g)
        old = Counter(c for g in self.table for c in g)
        if any(new[c] < n for c, n in old.items()):
            raise IllegalMove("a table card went missing")
        played = new - old
        if not played:
            raise IllegalMove("play at least one card from your hand")
        have = Counter(self.hands[seat])
        if any(have[c] < n for c, n in played.items()):
            raise IllegalMove("cards not in your hand")
        return groups, played

    def _play(self, seat: int, table: object) -> None:
        groups, played = self.check_play(seat, table)
        for c in played.elements():
            self.hands[seat].remove(c)
        self.table = groups
        self.passes = 0
        self.log.add("play", seat=seat, cards=sorted(played.elements()))
        if not self.hands[seat]:
            self.ended = True
            self.result = [seat]
            self.reason = "out"
            self.log.add("out", seat=seat)
            return
        self._next()

    def _next(self) -> None:
        self.turn = (self.turn + 1) % self.seats

    def _end_blocked(self) -> None:
        self.ended = True
        self.reason = "blocked"
        keys = [(len(h), sum(card_points(c) for c in h)) for h in self.hands]
        best = min(keys)
        self.result = [s for s, k in enumerate(keys) if k == best]
        self.log.add("end", reason="blocked", seats=self.result)

    # --- the end -----------------------------------------------------------------------------

    def winners(self) -> list[int]:
        return list(self.result) if self.ended else []

    def summary(self) -> dict[str, Any]:
        return {
            "winners": self.winners(),
            "reason": self.reason,
            "cards": [len(h) for h in self.hands],
            "points": [sum(card_points(c) for c in h) for h in self.hands],
        }

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        table, placed = self.bot_plan(seat)
        if placed:
            return {"type": "play", "table": table}
        return {"type": "draw"}

    def bot_plan(self, seat: int) -> tuple[list[list[str]], int]:
        """A new table and how many hand cards it places: (a) new melds from the hand, (b) hand
        cards added to table melds, (c) a bounded rebuild of the melds a card could touch."""
        hand = list(self.hands[seat])
        table = [list(g) for g in self.table]
        placed = 0
        melds = best_partition(hand, find_melds(hand, jokers=False), _size)
        for m in melds:
            table.append(m)
            for c in m:
                hand.remove(c)
                placed += 1
        progress = True
        while progress and hand:
            progress = False
            for c in sorted(set(hand)):
                for i, g in enumerate(table):
                    meld = analyse([*g, c], jokers=False)
                    if meld is not None:
                        table[i] = list(meld.cards)
                        hand.remove(c)
                        placed += 1
                        progress = True
                        break
        deadline = time.monotonic() + SEARCH_SECONDS
        for c in sorted(set(hand)):
            if time.monotonic() > deadline:
                break
            rebuilt = _rebuild(table, c, deadline)
            if rebuilt is not None:
                table = rebuilt
                hand.remove(c)
                placed += 1
        return table, placed

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        return {
            "hand": list(self.hands[seat]) if seat is not None else [],
            "handCounts": [len(h) for h in self.hands],
            "table": [list(g) for g in self.table],
            "stock": len(self.stock),
            "turn": None if self.ended else self.turn,
            "passes": self.passes,
            "winners": self.winners() if self.ended else None,
        }


def _rebuild(table: list[list[str]], card: str, deadline: float) -> list[list[str]] | None:
    """Fit `card` into the table by re-partitioning only the groups it could touch (sets of its
    rank, runs of its suit, and the groups that could lend a card to those)
    together with it. None if the bounded search finds nothing."""
    touched = []
    for i, g in enumerate(table):
        meld = analyse(g, jokers=False)
        kind = meld.kind if meld else "set"
        own = g[0][0] == card[0] if kind == "set" else g[0][1] == card[1]
        donor = (
            any(c[1] == card[1] for c in g) if kind == "set" else any(c[0] == card[0] for c in g)
        )
        if own or donor:
            touched.append(i)
    pool = [card] + [c for i in touched for c in table[i]]
    parts = _exact_partition(Counter(pool), deadline)
    if parts is None:
        return None
    keep = [g for i, g in enumerate(table) if i not in touched]
    return keep + parts


def _exact_partition(pool: Counter[str], deadline: float) -> list[list[str]] | None:
    """Split every card of `pool` into valid melds (no jokers), depth-first, bounded."""
    nodes = 0

    def candidates(first: str, avail: Counter[str]) -> list[list[str]]:
        out: list[list[str]] = []
        r, s = first[0], first[1]
        others = [r + t for t in "shdc" if t != s and avail[r + t] > 0]
        for mask in range(1, 1 << len(others)):
            group = [first] + [o for k, o in enumerate(others) if mask >> k & 1]
            if len(group) >= 3:
                out.append(group)
        # Runs through `first`: positions 1 (low ace) .. 14 (high ace), only over available cards.
        for p in [1, 14] if r == "A" else [FR_RANKS.index(r) + 2]:
            lo = hi = p
            while lo > 1 and avail[_at(lo - 1, s)] > 0:
                lo -= 1
            while hi < 14 and avail[_at(hi + 1, s)] > 0:
                hi += 1
            for a in range(lo, p + 1):
                for b in range(max(p, a + 2), min(hi, a + 12) + 1):
                    out.append([first] + [_at(q, s) for q in range(a, b + 1) if q != p])
        return out

    def dfs(avail: Counter[str]) -> list[list[str]] | None:
        nonlocal nodes
        nodes += 1
        if nodes > SEARCH_NODES or time.monotonic() > deadline:
            return None
        left = sorted(+avail)
        if not left:
            return []
        for group in candidates(left[0], avail):
            need = Counter(group)
            if any(avail[c] < n for c, n in need.items()):
                continue
            avail.subtract(need)
            found = dfs(avail)
            avail.update(need)
            if found is not None:
                meld = analyse(group, jokers=False)
                assert meld is not None
                return [list(meld.cards), *found]
        return None

    return dfs(+pool)


def _at(pos: int, suit: str) -> str:
    return ("A" if pos in (1, 14) else FR_RANKS[pos - 2]) + suit
