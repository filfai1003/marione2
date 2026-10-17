"""La Slot di Marione: 5 reels x 3 rows, 10 fixed paylines, one spin per round.

Symbols (keys for the artwork), from the richest: "marione" (the chef, wild), "spaghetti",
"pizza", "mandolino", "vespa", "moka", "pomodoro", "basilico", and "coin" (a Marioncello, the
scatter).

* A line pays for 3, 4 or 5 equal symbols from the leftmost reel. The wild stands in for every
  symbol but the coin; a line of wilds alone pays as "marione" when that is worth more.
* Line pays are multiples of the line bet (bet / 10); the total win is floored to whole coins.
* 3, 4 or 5 coins anywhere pay 2x, 10x, 50x the whole bet (on top of the lines).

Paylines (row of each reel, 0 = top, 1 = middle, 2 = bottom):

    0 middle   [1,1,1,1,1]     5 [0,0,1,2,2]
    1 top      [0,0,0,0,0]     6 [2,2,1,0,0]
    2 bottom   [2,2,2,2,2]     7 [1,0,0,0,1]
    3 V        [0,1,2,1,0]     8 [1,2,2,2,1]
    4 ^        [2,1,0,1,2]     9 [1,0,1,0,1]

Reel strips are fixed and built once from the weights below; RTP is about 95% (see
`theoretical_rtp`, checked by the tests).
"""

import random
from itertools import product
from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode

WILD = "marione"
SCATTER = "coin"
SYMBOLS = (
    "marione",
    "spaghetti",
    "pizza",
    "mandolino",
    "vespa",
    "moka",
    "pomodoro",
    "basilico",
    "coin",
)
REELS = 5
ROWS = 3
LINES = 10
MAX_BET = 100_000

PAYLINES: tuple[tuple[int, ...], ...] = (
    (1, 1, 1, 1, 1),
    (0, 0, 0, 0, 0),
    (2, 2, 2, 2, 2),
    (0, 1, 2, 1, 0),
    (2, 1, 0, 1, 2),
    (0, 0, 1, 2, 2),
    (2, 2, 1, 0, 0),
    (1, 0, 0, 0, 1),
    (1, 2, 2, 2, 1),
    (1, 0, 1, 0, 1),
)

# Multiples of the line bet for 3, 4, 5 of a kind.
PAYTABLE: dict[str, dict[int, int]] = {
    "marione": {3: 50, 4: 200, 5: 1000},
    "spaghetti": {3: 25, 4: 100, 5: 400},
    "pizza": {3: 20, 4: 60, 5: 200},
    "mandolino": {3: 15, 4: 40, 5: 120},
    "vespa": {3: 10, 4: 30, 5: 80},
    "moka": {3: 6, 4: 20, 5: 50},
    "pomodoro": {3: 5, 4: 12, 5: 30},
    "basilico": {3: 2, 4: 8, 5: 20},
}
# Multiples of the whole bet for coins anywhere.
SCATTER_PAYS: dict[int, int] = {3: 2, 4: 10, 5: 50}

# How many times each symbol appears on each reel (left to right).
WEIGHTS: dict[str, tuple[int, int, int, int, int]] = {
    "marione": (2, 2, 2, 2, 2),
    "spaghetti": (2, 2, 2, 2, 2),
    "pizza": (3, 3, 3, 3, 3),
    "mandolino": (3, 3, 3, 3, 3),
    "vespa": (4, 4, 4, 4, 4),
    "moka": (4, 4, 4, 4, 4),
    "pomodoro": (5, 5, 5, 5, 5),
    "basilico": (6, 6, 6, 6, 6),
    "coin": (2, 2, 2, 2, 2),
}


def _build_strip(reel: int) -> tuple[str, ...]:
    """A fixed strip for one reel: the weighted symbols in a fixed pseudo-random order."""
    cells = [s for s in SYMBOLS for _ in range(WEIGHTS[s][reel])]
    random.Random(f"marione-slot-{reel}").shuffle(cells)
    return tuple(cells)


STRIPS: tuple[tuple[str, ...], ...] = tuple(_build_strip(r) for r in range(REELS))


def window(reel: int, stop: int) -> list[str]:
    """The three symbols visible on `reel` when it stops at `stop` (top to bottom)."""
    strip = STRIPS[reel]
    return [strip[(stop + i) % len(strip)] for i in range(ROWS)]


def line_pay(symbols: list[str] | tuple[str, ...]) -> tuple[str, int, int]:
    """(symbol, count, multiple of the line bet) for the symbols on one line, left to right."""
    wilds = 0
    while wilds < len(symbols) and symbols[wilds] == WILD:
        wilds += 1
    wild_pay = PAYTABLE[WILD].get(wilds, 0)
    best = (WILD, wilds, wild_pay)
    if wilds < len(symbols) and symbols[wilds] != SCATTER:
        target = symbols[wilds]
        count = wilds
        while count < len(symbols) and symbols[count] in (target, WILD):
            count += 1
        pay = PAYTABLE[target].get(count, 0)
        if pay and pay >= wild_pay:
            best = (target, count, pay)
    return best if best[2] else ("", 0, 0)


def evaluate(grid: list[list[str]], bet: int) -> dict[str, Any]:
    """Every win on a grid (grid[reel][row]) for a total bet."""
    lines: list[dict[str, Any]] = []
    tenths = 0  # line pays are in line bets = tenths of the bet
    for i, rows in enumerate(PAYLINES):
        sym, count, mult = line_pay([grid[r][row] for r, row in enumerate(rows)])
        if mult:
            tenths += mult
            cells = [[r, rows[r]] for r in range(count)]
            lines.append(
                {
                    "line": i,
                    "symbol": sym,
                    "count": count,
                    "pay": bet * mult // LINES,
                    "cells": cells,
                }
            )
    coins = [[r, row] for r in range(REELS) for row in range(ROWS) if grid[r][row] == SCATTER]
    scatter_mult = SCATTER_PAYS.get(min(len(coins), 5), 0)
    scatter_pay = bet * scatter_mult
    win = bet * tenths // LINES + scatter_pay
    return {
        "lines": lines,
        "scatter": {"count": len(coins), "pay": scatter_pay, "cells": coins if scatter_pay else []},
        "win": win,
    }


def theoretical_rtp() -> float:
    """Exact return to player (lines + scatter), from the strips: reels are independent and every
    row of a reel shows each symbol with its strip frequency."""
    probs = [{s: WEIGHTS[s][r] / len(STRIPS[r]) for s in SYMBOLS} for r in range(REELS)]
    line_ev = 0.0
    for combo in product(SYMBOLS, repeat=REELS):
        mult = line_pay(combo)[2]
        if mult:
            p = 1.0
            for r, s in enumerate(combo):
                p *= probs[r][s]
            line_ev += p * mult
    # Distribution of the number of coins: per reel, over its stops; then convolve.
    dist = [1.0]
    for r in range(REELS):
        n = len(STRIPS[r])
        per = [0.0] * (ROWS + 1)
        for stop in range(n):
            per[window(r, stop).count(SCATTER)] += 1 / n
        new = [0.0] * (len(dist) + ROWS)
        for a, pa in enumerate(dist):
            for b, pb in enumerate(per):
                new[a + b] += pa * pb
        dist = new
    scatter_ev = sum(p * SCATTER_PAYS.get(min(k, 5), 0) for k, p in enumerate(dist))
    # Each of the 10 lines costs a tenth of the bet: line_ev line bets per line = line_ev bets.
    return line_ev + scatter_ev


class Slot(Game):
    key: ClassVar[str] = "slot"
    modes: ClassVar[tuple[Mode, ...]] = (Mode("solo", 1),)
    economy = "bets"
    house = True

    def __init__(
        self, mode: Mode, rng: random.Random, options: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mode, rng, options)
        self.max_bet = min(MAX_BET, max(1000, 50 * self.stake))
        self.grid = self._spin_grid()  # an idle grid before the spin
        self.bet = 0
        self.result: dict[str, Any] | None = None

    def _spin_grid(self) -> list[list[str]]:
        return [window(r, self.rng.randrange(len(STRIPS[r]))) for r in range(REELS)]

    def _amount(self, action: Action) -> int:
        if self.finished:
            raise IllegalMove("already spun")
        if action.get("type") != "spin":
            raise IllegalMove("unknown action")
        amount = action.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise IllegalMove("bad amount")
        if not 1 <= amount <= self.max_bet:
            raise IllegalMove("bet out of range")
        return amount

    def to_act(self) -> list[int]:
        return [] if self.finished else [0]

    def legal(self, seat: int) -> list[Action]:
        if seat != 0 or self.finished:
            return []
        return [{"type": "spin", "min": 1, "max": self.max_bet}]

    def cost(self, seat: int, action: Action) -> int:
        if seat != 0:
            raise IllegalMove("no such seat")
        return self._amount(action)

    def act(self, seat: int, action: Action) -> None:
        if seat != 0:
            raise IllegalMove("no such seat")
        self.bet = self._amount(action)
        self.grid = self._spin_grid()
        self.result = evaluate(self.grid, self.bet)
        self.log.add("spin", seat=0, bet=self.bet, win=self.result["win"])

    @property
    def finished(self) -> bool:
        return self.result is not None

    def payouts(self) -> dict[int, int]:
        return {0: self.result["win"]} if self.result else {}

    def summary(self) -> dict[str, Any]:
        return {"bet": self.bet, "win": self.result["win"] if self.result else 0}

    def bot_action(self, seat: int) -> Action:
        return {"type": "spin", "amount": min(self.max_bet, max(1, self.stake))}

    def view(self, seat: int | None) -> dict[str, Any]:
        res = self.result
        return {
            "grid": [list(col) for col in self.grid],
            "spun": res is not None,
            "bet": self.bet,
            "maxBet": self.max_bet,
            "win": res["win"] if res else 0,
            "lines": res["lines"] if res else [],
            "scatter": res["scatter"] if res else {"count": 0, "pay": 0, "cells": []},
            "paytable": {
                s: {str(k): v / LINES for k, v in pays.items()} for s, pays in PAYTABLE.items()
            },
            "scatterPays": {str(k): v for k, v in SCATTER_PAYS.items()},
            "paylines": [list(p) for p in PAYLINES],
            "wild": WILD,
            "scatterSymbol": SCATTER,
        }
