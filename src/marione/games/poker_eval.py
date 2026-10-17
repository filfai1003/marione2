"""Poker shared code: the hand evaluator and a fixed-limit betting engine.

`evaluate` takes 5..7 French cards ("Ah", "Td") and returns the best five-card hand as a
comparable rank ``(category, tiebreakers)`` plus a name key. The ace also plays low in the wheel
(A-2-3-4-5, a five-high straight).

`LimitPoker` is the betting machinery `Poker5` and `Texas` share. One object is ONE hand:

* a posting phase: forced payments asked in turn (antes or blinds, the action type is
  `post_type`); a seat may fold instead and sits the hand out;
* betting rounds: fold / check / call / bet / raise with fixed sizes, at most `MAX_BETS` bets per
  round (the bet plus three raises; a big blind counts as the first bet);
* the end: one seat left wins the pot without a showdown, otherwise the best hand wins and ties
  split the pot, odd chips going one each to the winners from the button's left.

There is no all-in: the table refuses an action whose cost a human cannot pay, and folding or
checking is always free. So every seat still in at a showdown has put in the same amount and a
single pot is enough.
"""

from collections import Counter
from itertools import combinations
from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode
from marione.games.cards import fr_value, suit

HandRank = tuple[int, tuple[int, ...]]

HIGH_CARD, PAIR, TWO_PAIR, THREE, STRAIGHT, FLUSH, FULL_HOUSE, FOUR, STRAIGHT_FLUSH = range(9)
NAMES = (
    "high_card",
    "pair",
    "two_pair",
    "three",
    "straight",
    "flush",
    "full_house",
    "four",
    "straight_flush",
)
MAX_BETS = 4


def _straight_top(values: list[int]) -> int | None:
    """Top card of a straight among five distinct values (5 for the wheel), else None."""
    vs = sorted(set(values), reverse=True)
    if len(vs) != 5:
        return None
    if vs[0] - vs[4] == 4:
        return vs[0]
    if vs == [14, 5, 4, 3, 2]:
        return 5
    return None


def evaluate5(cards: list[str] | tuple[str, ...]) -> HandRank:
    """Rank exactly five cards."""
    if len(cards) != 5:
        raise ValueError("five cards needed")
    values = [fr_value(c) for c in cards]
    flush = len({suit(c) for c in cards}) == 1
    top = _straight_top(values)
    counts = Counter(values)
    # Groups by size, then by value: e.g. full house 8-8-8-K-K -> [(3, 8), (2, 13)].
    groups = sorted(((n, v) for v, n in counts.items()), reverse=True)
    ordered = tuple(v for _, v in groups)
    if top is not None and flush:
        return (STRAIGHT_FLUSH, (top,))
    if groups[0][0] == 4:
        return (FOUR, ordered)
    if groups[0][0] == 3 and groups[1][0] == 2:
        return (FULL_HOUSE, ordered)
    if flush:
        return (FLUSH, tuple(sorted(values, reverse=True)))
    if top is not None:
        return (STRAIGHT, (top,))
    if groups[0][0] == 3:
        return (THREE, ordered)
    if groups[0][0] == 2 and groups[1][0] == 2:
        return (TWO_PAIR, ordered)
    if groups[0][0] == 2:
        return (PAIR, ordered)
    return (HIGH_CARD, ordered)


def rank_name(rank: HandRank) -> str:
    if rank[0] == STRAIGHT_FLUSH and rank[1][0] == 14:
        return "royal_flush"
    return NAMES[rank[0]]


def best_five(cards: list[str]) -> tuple[HandRank, list[str]]:
    """The best five-card hand among 5..7 cards, with the cards that make it."""
    if not 5 <= len(cards) <= 7:
        raise ValueError("5 to 7 cards needed")
    best: tuple[HandRank, list[str]] | None = None
    for combo in combinations(cards, 5):
        r = evaluate5(combo)
        if best is None or r > best[0]:
            best = (r, list(combo))
    assert best is not None
    return best


def evaluate(cards: list[str]) -> tuple[HandRank, str]:
    """Best hand among 5..7 cards: (comparable rank, name key)."""
    r, _ = best_five(cards)
    return r, rank_name(r)


# --- the betting engine ----------------------------------------------------------------------


def seat_modes(low: int, high: int) -> tuple[Mode, ...]:
    return tuple(Mode(f"{n}p", n) for n in range(low, high + 1))


class LimitPoker(Game):
    """One hand of fixed-limit poker; subclasses deal the cards and drive the streets."""

    economy = "bets"
    house = False
    post_type: ClassVar[str] = "ante"  # the forced action: "ante" or "blind"
    post_phase: ClassVar[str] = "ante"  # the phase name while forced bets are collected
    betting_phases: ClassVar[tuple[str, ...]] = ()

    def __init__(self, mode: Mode, rng: Any, options: dict[str, Any] | None = None) -> None:
        super().__init__(mode, rng, options)
        n = mode.seats
        self.unit = max(1, self.stake)
        self.button = int(self.options.get("button", 0)) % n
        self.phase = self.post_phase
        self.hands: list[list[str]] = [[] for _ in range(n)]
        self.folded = [False] * n
        self.contributed = [0] * n  # everything put in this hand
        self.bets = [0] * n  # this betting round
        self.current_bet = 0
        self.raises = 0  # bets made this round (bet + raises)
        self.pending: list[int] = []  # seats still to act this round, in order
        self.post_queue: list[int] = []
        self.post_amounts: list[int] = []
        self.posted: list[int] = []  # seats that paid a forced bet, in order
        self.done = False
        self.reason = ""
        self.winner_seats: list[int] = []
        self.won: dict[int, int] = {}
        self.showdown: list[dict[str, Any]] | None = None

    # --- helpers -----------------------------------------------------------------------------

    def order_from(self, start: int) -> list[int]:
        return [(start + i) % self.seats for i in range(self.seats)]

    def active(self) -> list[int]:
        return [s for s in range(self.seats) if not self.folded[s]]

    @property
    def pot(self) -> int:
        return sum(self.contributed)

    def bet_size(self) -> int:
        """The fixed bet of the current round."""
        return self.unit

    def to_call(self, seat: int) -> int:
        return max(0, self.current_bet - self.bets[seat])

    def start_round(self, first: int) -> None:
        """A fresh betting round: nobody has bet yet, first to act is the first active seat
        from `first`."""
        self.bets = [0] * self.seats
        self.current_bet = 0
        self.raises = 0
        self.pending = [s for s in self.order_from(first) if not self.folded[s]]

    @property
    def turn(self) -> int | None:
        if self.done:
            return None
        if self.phase == self.post_phase:
            return self.post_queue[0] if self.post_queue else None
        return self.pending[0] if self.pending else None

    # --- hooks for the subclasses ------------------------------------------------------------

    def after_posting(self) -> None:
        raise NotImplementedError

    def round_over(self) -> None:
        """A betting (or drawing) round has ended: move on to the next street or showdown."""
        raise NotImplementedError

    def eval_cards(self, seat: int) -> list[str]:
        return self.hands[seat]

    def posts_are_bets(self) -> bool:
        """Blinds count as bets of the first round; antes are dead money."""
        return False

    def other_legal(self, seat: int) -> list[Action]:
        """Legal actions in a phase that is neither posting nor betting (the draw)."""
        return []

    def other_act(self, seat: int, action: Action) -> None:
        raise IllegalMove("bad action")

    # --- the contract ------------------------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.done

    def to_act(self) -> list[int]:
        t = self.turn
        return [] if t is None else [t]

    def betting(self) -> bool:
        return self.phase in self.betting_phases and not self.done

    def legal(self, seat: int) -> list[Action]:
        if seat != self.turn:
            return []
        if self.phase == self.post_phase:
            return [
                {"type": self.post_type, "cost": self.post_amounts[0]},
                {"type": "fold", "cost": 0},
            ]
        if not self.betting():
            return self.other_legal(seat)
        owed = self.to_call(seat)
        out: list[Action] = [{"type": "fold", "cost": 0}]
        out.append({"type": "check", "cost": 0} if owed == 0 else {"type": "call", "cost": owed})
        if self.raises < MAX_BETS:
            kind = "bet" if self.current_bet == 0 else "raise"
            out.append({"type": kind, "cost": owed + self.bet_size()})
        return out

    def cost(self, seat: int, action: Action) -> int:
        if seat != self.turn:
            raise IllegalMove("not your turn")
        kind = action.get("type")
        if self.phase == self.post_phase or self.betting():
            for entry in self.legal(seat):
                if entry["type"] == kind:
                    return int(entry["cost"])
            raise IllegalMove("action not allowed now")
        return 0

    def act(self, seat: int, action: Action) -> None:
        paid = self.cost(seat, action)  # validates turn and type
        kind = str(action.get("type"))
        if self.phase == self.post_phase:
            self._post(seat, kind, paid)
            return
        if not self.betting():
            self.other_act(seat, action)
            return
        self.pending.pop(0)
        if kind == "fold":
            self._fold(seat)
            return
        self.bets[seat] += paid
        self.contributed[seat] += paid
        if kind in ("bet", "raise"):
            self.raises += 1
            self.current_bet = self.bets[seat]
            after = self.order_from(seat)[1:]
            self.pending = [s for s in after if not self.folded[s]]
        self.log.add(kind, seat=seat, amount=paid)
        if not self.pending:
            self.round_over()

    def _post(self, seat: int, kind: str, paid: int) -> None:
        self.post_queue.pop(0)
        if kind == "fold":
            self._fold(seat)
        else:
            self.post_amounts.pop(0)
            self.contributed[seat] += paid
            if self.posts_are_bets():
                self.bets[seat] += paid
                self.current_bet = max(self.current_bet, self.bets[seat])
            self.posted.append(seat)
            self.log.add(self.post_type, seat=seat, amount=paid)
        if not self.done and (not self.post_amounts or not self.post_queue):
            self.post_queue = []
            self.after_posting()

    def _fold(self, seat: int) -> None:
        self.folded[seat] = True
        self.pending = [s for s in self.pending if s != seat]
        self.post_queue = [s for s in self.post_queue if s != seat]
        self.log.add("fold", seat=seat)
        left = self.active()
        if len(left) == 1:
            self._award(left, "fold")
        elif (self.betting() and not self.pending) or (self.phase == "draw" and not self.pending):
            self.round_over()

    # --- the end -----------------------------------------------------------------------------

    def do_showdown(self) -> None:
        ranks: dict[int, HandRank] = {}
        self.showdown = []
        for s in self.order_from((self.button + 1) % self.seats):
            if self.folded[s]:
                continue
            r, five = best_five(self.eval_cards(s))
            ranks[s] = r
            self.showdown.append(
                {"seat": s, "cards": list(self.hands[s]), "best": five, "rank": rank_name(r)}
            )
        top = max(ranks.values())
        self._award([s for s in ranks if ranks[s] == top], "showdown")

    def _award(self, winners: list[int], reason: str) -> None:
        start = (self.button + 1) % self.seats
        winners = sorted(winners, key=lambda s: (s - start) % self.seats)
        pot = self.pot
        share, odd = divmod(pot, len(winners))
        self.won = {s: share + (1 if i < odd else 0) for i, s in enumerate(winners)}
        self.winner_seats = winners
        self.reason = reason
        self.done = True
        self.phase = "showdown" if reason == "showdown" else "over"
        self.pending = []
        self.post_queue = []
        for s in winners:
            self.log.add("win", seat=s, amount=self.won[s])

    def winners(self) -> list[int]:
        return list(self.winner_seats)

    def payouts(self) -> dict[int, int]:
        return {s: v for s, v in self.won.items() if v > 0}

    def summary(self) -> dict[str, Any]:
        names = {e["seat"]: e["rank"] for e in self.showdown or []}
        return {
            "winners": self.winners(),
            "won": {str(s): v for s, v in self.won.items()},
            "pot": self.pot,
            "reason": self.reason,
            "hands": self.showdown or [],
            "winningHand": names.get(self.winner_seats[0]) if self.winner_seats else None,
        }

    def base_view(self, seat: int | None) -> dict[str, Any]:
        own: list[str] = list(self.hands[seat]) if seat is not None else []
        return {
            "phase": self.phase,
            "hand": own,
            "handName": rank_name(best_five(self.eval_cards(seat))[0])
            if seat is not None and 5 <= len(self.eval_cards(seat)) <= 7
            else None,
            "handCounts": [len(h) for h in self.hands],
            "pot": self.pot,
            "bets": list(self.bets),
            "contributed": list(self.contributed),
            "folded": list(self.folded),
            "button": self.button,
            "turn": self.turn,
            "toCall": self.to_call(seat) if seat is not None and self.betting() else 0,
            "currentBet": self.current_bet,
            "betSize": self.bet_size(),
            "raises": self.raises,
            "maxBets": MAX_BETS,
            "unit": self.unit,
            "showdown": self.showdown,
            "winners": self.winners(),
            "won": {str(s): v for s, v in self.won.items()},
        }

    # --- bot helpers -------------------------------------------------------------------------

    def bot_bet(self, seat: int, strength: float) -> Action:
        """Pick a betting action from a strength in 0..1, with a little bluffing."""
        legal = {a["type"]: a for a in self.legal(seat)}
        owed = self.to_call(seat)
        aggressive = legal.get("bet") or legal.get("raise")
        bluff = self.rng.random() < 0.08
        strong = strength >= 0.7 or (bluff and strength >= 0.2)
        if aggressive is not None and strong and (self.raises < 2 or strength >= 0.85):
            return dict(aggressive)
        if owed == 0:
            if aggressive is not None and strength >= 0.55 and self.rng.random() < 0.5:
                return dict(aggressive)
            return dict(legal["check"])
        pot_odds = owed * 4 <= self.pot + owed
        if strength >= 0.4 or (pot_odds and strength >= 0.25) or bluff:
            return dict(legal["call"])
        return dict(legal["fold"])

    def bot_post(self, seat: int) -> Action:
        return {"type": self.post_type, "cost": self.post_amounts[0]}
