"""Scala 40: rummy with two French decks and four jokers (108 cards), 2 to 6 players.

Thirteen cards each; one card face up starts the discard pile, the rest is the stock. A turn:

1. **draw** one card, from the stock or the top of the discard pile. Taking the discard is allowed
   only to someone who has opened or who opens in this same turn, and that card must go onto the
   table this turn (in a new meld, laid off, or swapped for a joker). The engine only offers it when
   it can see a way to use it.
2. optionally **meld**: lay new melds from the hand (see `melds.py`; one joker per meld at most).
   The first time (the *opening*) a single meld action must total at least 40 points. Once opened
   you may also **lay off** cards onto any meld on the table and **swap a joker** on the table for
   the real card it stands for (the joker goes to your hand).
3. **discard** one card: the turn ends. Melding and laying off must always leave at least one card
   in hand, because you go out only by discarding your last card. Whoever goes out wins the match.

When the stock runs out the discard pile, except its top card, is shuffled into a new stock. Safety
end (so a table of players who never go out cannot run forever): the fourth time the stock runs
out, or when there is nothing to reshuffle, the match ends and the lowest penalty in hand (joker 25,
ace 11, figures 10, numbers face value) wins; a tie is a draw.
"""

from collections import Counter
from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode
from marione.games.cards import french_deck, is_joker, shuffled
from marione.games.melds import (
    analyse,
    best_partition,
    card_points,
    find_melds,
    meld_points,
    valid_card,
)

OPENING = 40
HAND = 13
MAX_RESHUFFLES = 3


def _score(meld: Any) -> int:
    return meld_points(meld)


class Scala40(Game):
    key: ClassVar[str] = "scala40"
    economy = "stake"
    modes: ClassVar[tuple[Mode, ...]] = tuple(Mode(f"{n}p", n) for n in range(2, 7))

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        self.stock = shuffled(french_deck(copies=2, jokers=4), rng)
        self.hands: list[list[str]] = [[] for _ in range(mode.seats)]
        for _ in range(HAND):
            for s in range(mode.seats):
                self.hands[s].append(self.stock.pop())
        self.discard: list[str] = [self.stock.pop()]
        self.table: list[dict[str, Any]] = []  # {"cards", "owner", "kind"}
        self.opened = [False] * mode.seats
        self.turn = 0
        self.phase = "draw"
        self.must_use: str | None = None
        self.reshuffles = 0
        self.winner: int | None = None
        self.ended = False
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
        hand = self.hands[seat]
        if self.phase == "draw":
            out: list[Action] = [{"type": "draw", "from": "stock"}]
            if self._discard_use(seat) is not None:
                out.append({"type": "draw", "from": "discard"})
            return out
        out = []
        if self.must_use is None:
            out += [{"type": "discard", "card": c} for c in sorted(set(hand))]
        if len(hand) >= 4:
            suggested = self._suggest(seat)
            if suggested:
                out.append({"type": "meld", "suggested": suggested})
            out.append({"type": "meld"})
        if self.opened[seat] and len(hand) >= 2:
            for i, m in enumerate(self.table):
                for c in sorted(set(hand)):
                    if analyse([*m["cards"], c]) is not None:
                        out.append({"type": "layoff", "meld": i, "cards": [c]})
                    if any(is_joker(x) for x in m["cards"]) and self._swap_ok(m["cards"], c):
                        out.append({"type": "swap_joker", "meld": i, "card": c})
            out.append({"type": "layoff"})
        return out

    def act(self, seat: int, action: Action) -> None:
        if self.ended or seat != self.turn:
            raise IllegalMove("not your turn")
        kind = action.get("type")
        if self.phase == "draw":
            if kind != "draw":
                raise IllegalMove("draw first")
            self._draw(seat, action.get("from"))
            return
        if kind == "meld":
            self._meld(seat, action.get("melds"))
        elif kind == "layoff":
            self._layoff(seat, action.get("meld"), action.get("cards"))
        elif kind == "swap_joker":
            self._swap(seat, action.get("meld"), action.get("card"))
        elif kind == "discard":
            self._discard(seat, action.get("card"))
        else:
            raise IllegalMove("unknown action")

    def _draw(self, seat: int, source: object) -> None:
        if source == "discard":
            if self._discard_use(seat) is None:
                raise IllegalMove("you cannot use the top discard")
            card = self.discard.pop()
            self.hands[seat].append(card)
            self.must_use = card
            self.log.add("draw", seat=seat, source="discard", card=card)
        elif source == "stock":
            if not self.stock and not self._reshuffle():
                return
            self.hands[seat].append(self.stock.pop())
            self.log.add("draw", seat=seat, source="stock")
        else:
            raise IllegalMove("draw from stock or discard")
        self.phase = "play"

    def _reshuffle(self) -> bool:
        if self.reshuffles >= MAX_RESHUFFLES or len(self.discard) < 2:
            self._end_stalled()
            return False
        top = self.discard.pop()
        self.stock = shuffled(self.discard, self.rng)
        self.discard = [top]
        self.reshuffles += 1
        self.log.add("reshuffle", cards=len(self.stock))
        return True

    def _end_stalled(self) -> None:
        self.ended = True
        self.reason = "stock"
        pens = self.penalties()
        low = min(pens)
        self.winner = pens.index(low) if pens.count(low) == 1 else None
        self.log.add("end", reason="stock", seat=self.winner)

    def _take(self, seat: int, cards: list[str]) -> None:
        """Check `cards` are in the hand (as a multiset) and leave at least one; then remove."""
        hand = self.hands[seat]
        need = Counter(cards)
        have = Counter(hand)
        if any(have[c] < n for c, n in need.items()):
            raise IllegalMove("cards not in hand")
        if len(cards) >= len(hand):
            raise IllegalMove("keep a card to discard")
        for c in cards:
            hand.remove(c)
        if self.must_use is not None and self.must_use in need:
            self.must_use = None

    def _meld(self, seat: int, melds: object) -> None:
        if not isinstance(melds, list) or not melds:
            raise IllegalMove("no melds")
        parsed = []
        for m in melds:
            if not isinstance(m, list) or not all(valid_card(c) for c in m):
                raise IllegalMove("bad meld")
            info = analyse(m)
            if info is None:
                raise IllegalMove("not a valid meld")
            parsed.append(info)
        total = sum(p.points for p in parsed)
        if not self.opened[seat] and total < OPENING:
            raise IllegalMove(f"opening needs {OPENING} points")
        self._take(seat, [c for p in parsed for c in p.cards])
        for p in parsed:
            self.table.append({"cards": list(p.cards), "owner": seat, "kind": p.kind})
        if not self.opened[seat]:
            self.opened[seat] = True
            self.log.add("open", seat=seat, points=total)
        self.log.add("meld", seat=seat, melds=[list(p.cards) for p in parsed])

    def _table_meld(self, index: object) -> dict[str, Any]:
        if not isinstance(index, int) or isinstance(index, bool):
            raise IllegalMove("bad meld index")
        if not 0 <= index < len(self.table):
            raise IllegalMove("no such meld")
        return self.table[index]

    def _layoff(self, seat: int, index: object, cards: object) -> None:
        if not self.opened[seat]:
            raise IllegalMove("open first")
        meld = self._table_meld(index)
        if not isinstance(cards, list) or not cards or not all(valid_card(c) for c in cards):
            raise IllegalMove("no cards")
        info = analyse([*meld["cards"], *cards])
        if info is None:
            raise IllegalMove("the meld would not be valid")
        self._take(seat, list(cards))
        meld["cards"] = list(info.cards)
        meld["kind"] = info.kind
        self.log.add("layoff", seat=seat, meld=index, cards=list(cards))

    def _swap_ok(self, cards: list[str], card: str) -> bool:
        if is_joker(card) or not any(is_joker(c) for c in cards):
            return False
        return analyse([card if is_joker(c) else c for c in cards], jokers=False) is not None

    def _swap(self, seat: int, index: object, card: object) -> None:
        if not self.opened[seat]:
            raise IllegalMove("open first")
        meld = self._table_meld(index)
        if not isinstance(card, str) or not valid_card(card) or card not in self.hands[seat]:
            raise IllegalMove("card not in hand")
        if not self._swap_ok(meld["cards"], card):
            raise IllegalMove("that card does not replace the joker")
        joker = next(c for c in meld["cards"] if is_joker(c))
        hand = self.hands[seat]
        hand.remove(card)
        hand.append(joker)
        if self.must_use == card:
            self.must_use = None
        info = analyse([card if c == joker else c for c in meld["cards"]], jokers=False)
        assert info is not None
        meld["cards"] = list(info.cards)
        self.log.add("swap", seat=seat, meld=index, card=card, joker=joker)

    def _discard(self, seat: int, card: object) -> None:
        hand = self.hands[seat]
        if not isinstance(card, str) or card not in hand:
            raise IllegalMove("card not in hand")
        if self.must_use is not None:
            raise IllegalMove("use the card taken from the discard pile first")
        hand.remove(card)
        self.discard.append(card)
        self.log.add("discard", seat=seat, card=card)
        if not hand:
            self.ended = True
            self.winner = seat
            self.reason = "out"
            self.log.add("out", seat=seat)
            return
        self.turn = (seat + 1) % self.seats
        self.phase = "draw"

    # --- helpers shared by legal and the bot ---------------------------------------------------

    def _discard_use(self, seat: int) -> Action | None:
        """How `seat` could use the top discard this turn (None: taking it is not allowed)."""
        if not self.discard:
            return None
        card = self.discard[-1]
        hand = [*self.hands[seat], card]
        if not self.opened[seat]:
            melds = best_partition(hand, find_melds(hand), _score, keep=1, required=card)
            if sum(meld_points(m) for m in melds) >= OPENING:
                return {"type": "meld", "melds": melds}
            return None
        for i, m in enumerate(self.table):
            if self._swap_ok(m["cards"], card):
                return {"type": "swap_joker", "meld": i, "card": card}
        for i, m in enumerate(self.table):
            if analyse([*m["cards"], card]) is not None:
                return {"type": "layoff", "meld": i, "cards": [card]}
        melds = best_partition(hand, find_melds(hand), _score, keep=1, required=card)
        return {"type": "meld", "melds": melds} if melds else None

    def _suggest(self, seat: int) -> list[list[str]]:
        hand = self.hands[seat]
        melds = best_partition(hand, find_melds(hand), _score, keep=1, required=self.must_use)
        if not self.opened[seat] and sum(meld_points(m) for m in melds) < OPENING:
            return []
        return melds

    def penalties(self) -> list[int]:
        return [sum(card_points(c) for c in h) for h in self.hands]

    # --- the end -----------------------------------------------------------------------------

    def winners(self) -> list[int]:
        return [self.winner] if self.ended and self.winner is not None else []

    def summary(self) -> dict[str, Any]:
        return {
            "winners": self.winners(),
            "reason": self.reason,
            "penalties": self.penalties(),
            "hands": [list(h) for h in self.hands],
        }

    # --- the computer player -----------------------------------------------------------------

    def bot_action(self, seat: int) -> Action:
        hand = self.hands[seat]
        if self.phase == "draw":
            if self._discard_use(seat) is not None:
                return {"type": "draw", "from": "discard"}
            return {"type": "draw", "from": "stock"}
        if self.must_use is not None:
            use = self._must_use_action(seat)
            if use is not None:
                return use
        if len(hand) >= 4:
            melds = self._suggest(seat)
            if melds:
                return {"type": "meld", "melds": melds}
        if self.opened[seat] and len(hand) >= 2:
            for c in sorted(set(hand), key=card_points, reverse=True):
                if is_joker(c):
                    continue
                for i, m in enumerate(self.table):
                    if self._swap_ok(m["cards"], c):
                        return {"type": "swap_joker", "meld": i, "card": c}
                    if analyse([*m["cards"], c]) is not None:
                        return {"type": "layoff", "meld": i, "cards": [c]}
        return {"type": "discard", "card": self._worst_card(hand)}

    def _must_use_action(self, seat: int) -> Action | None:
        card = self.must_use
        assert card is not None
        hand = self.hands[seat]
        melds = best_partition(hand, find_melds(hand), _score, keep=1, required=card)
        if melds and (self.opened[seat] or sum(meld_points(m) for m in melds) >= OPENING):
            return {"type": "meld", "melds": melds}
        if self.opened[seat]:
            for i, m in enumerate(self.table):
                if not is_joker(card) and self._swap_ok(m["cards"], card):
                    return {"type": "swap_joker", "meld": i, "card": card}
                if analyse([*m["cards"], card]) is not None:
                    return {"type": "layoff", "meld": i, "cards": [card]}
        return None

    def _worst_card(self, hand: list[str]) -> str:
        """The highest card outside any meld or near-meld; a joker only if nothing else."""

        def useful(card: str) -> int:
            if is_joker(card):
                return 3
            n = 0
            for other in hand:
                if other == card or is_joker(other):
                    continue
                same_rank = other[0] == card[0] and other[1] != card[1]
                near = other[1] == card[1] and _gap(card, other) <= 2
                n += int(same_rank or near)
            return min(n, 2)

        return min(hand, key=lambda c: (useful(c), -card_points(c), c))

    # --- view --------------------------------------------------------------------------------

    def view(self, seat: int | None) -> dict[str, Any]:
        return {
            "hand": list(self.hands[seat]) if seat is not None else [],
            "handCounts": [len(h) for h in self.hands],
            "table": [
                {"cards": list(m["cards"]), "owner": m["owner"], "kind": m["kind"]}
                for m in self.table
            ],
            "discardTop": self.discard[-1] if self.discard else None,
            "discardCount": len(self.discard),
            "stock": len(self.stock),
            "opened": list(self.opened),
            "phase": self.phase,
            "turn": None if self.ended else self.turn,
            "mustUse": self.must_use if seat == self.turn else None,
            "winner": self.winner,
            "penalties": self.penalties() if self.ended else None,
        }


def _gap(a: str, b: str) -> int:
    order = "A23456789TJQK"
    ia, ib = order.index(a[0]), order.index(b[0])
    d = abs(ia - ib)
    if "A" in (a[0], b[0]):
        d = min(d, 13 - d)
    return d
