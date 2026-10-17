"""European roulette (single zero) against the bank. One round: place any number of bets (each is
paid when placed and is final), then spin.

Bets and what they pay (net, the stake comes back on top):

* ``straight`` one number 0-36, target an int: 35 to 1
* ``split`` two adjacent numbers on the layout (0 with 1, 2 or 3), target [a, b]: 17 to 1
* ``street`` a row of three ([1,2,3] ... [34,35,36], also [0,1,2] and [0,2,3]): 11 to 1
* ``corner`` four numbers in a square ([1,2,4,5] ..., also [0,1,2,3]): 8 to 1
* ``line`` two rows, six numbers ([1..6] ... [31..36]), target a list: 5 to 1
* ``dozen`` target 1, 2 or 3 (1-12, 13-24, 25-36) and ``column`` target 1, 2 or 3: 2 to 1
* ``red``, ``black``, ``even``, ``odd``, ``low`` (1-18), ``high`` (19-36), no target: 1 to 1

The layout has three columns: column 1 is 1, 4, ..., 34; column 3 is 3, 6, ..., 36. Zero loses
every outside bet. House edge 1/37 = 2.7% on every bet.
"""

import random
from typing import Any, ClassVar

from marione.games.base import Action, Game, IllegalMove, Mode

WHEEL_ORDER: tuple[int, ...] = (
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30, 8, 23, 10,
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26,
)  # fmt: skip
RED: frozenset[int] = frozenset((1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36))
MAX_TOTAL = 100_000
MAX_BETS = 60

PAYS: dict[str, int] = {
    "straight": 35,
    "split": 17,
    "street": 11,
    "corner": 8,
    "line": 5,
    "dozen": 2,
    "column": 2,
    "red": 1,
    "black": 1,
    "even": 1,
    "odd": 1,
    "low": 1,
    "high": 1,
}


def color(n: int) -> str:
    return "green" if n == 0 else "red" if n in RED else "black"


def _sets() -> dict[str, set[tuple[int, ...]]]:
    splits: set[tuple[int, ...]] = {(0, 1), (0, 2), (0, 3)}
    for n in range(1, 37):
        if n % 3 != 0:
            splits.add((n, n + 1))
        if n <= 33:
            splits.add((n, n + 3))
    streets: set[tuple[int, ...]] = {(n, n + 1, n + 2) for n in range(1, 35, 3)} | {
        (0, 1, 2),
        (0, 2, 3),
    }
    corners: set[tuple[int, ...]] = {
        (n, n + 1, n + 3, n + 4) for n in range(1, 33) if n % 3 != 0
    } | {(0, 1, 2, 3)}
    lines: set[tuple[int, ...]] = {tuple(range(n, n + 6)) for n in range(1, 32, 3)}
    return {"split": splits, "street": streets, "corner": corners, "line": lines}


VALID_SETS = _sets()


def numbers_of(kind: str, target: Any) -> tuple[int, ...]:
    """The numbers a bet covers; IllegalMove if the bet or its target is not valid."""
    if kind not in PAYS:
        raise IllegalMove("unknown bet")
    if kind == "straight":
        if not isinstance(target, int) or isinstance(target, bool) or not 0 <= target <= 36:
            raise IllegalMove("bad number")
        return (target,)
    if kind in VALID_SETS:
        if not isinstance(target, list | tuple) or not all(
            isinstance(n, int) and not isinstance(n, bool) for n in target
        ):
            raise IllegalMove("bad target")
        nums = tuple(sorted(target))
        if nums not in VALID_SETS[kind]:
            raise IllegalMove(f"not a valid {kind}")
        return nums
    if kind in ("dozen", "column"):
        if target not in (1, 2, 3) or isinstance(target, bool):
            raise IllegalMove("bad target")
        if kind == "dozen":
            return tuple(range(12 * target - 11, 12 * target + 1))
        return tuple(range(target, 37, 3))
    if target is not None:
        raise IllegalMove("this bet takes no target")
    return tuple(n for n in range(1, 37) if _outside(kind, n))


def _outside(kind: str, n: int) -> bool:
    if kind in ("red", "black"):
        return (n in RED) == (kind == "red")
    if kind in ("even", "odd"):
        return n % 2 == (0 if kind == "even" else 1)
    return n <= 18 if kind == "low" else n >= 19


class Roulette(Game):
    key: ClassVar[str] = "roulette"
    modes: ClassVar[tuple[Mode, ...]] = (Mode("solo", 1),)
    economy = "bets"
    house = True

    def __init__(
        self, mode: Mode, rng: random.Random, options: dict[str, Any] | None = None
    ) -> None:
        super().__init__(mode, rng, options)
        self.max_total = min(MAX_TOTAL, max(1000, 50 * self.stake))
        self.bets: list[dict[str, Any]] = []
        self.result: int | None = None

    @property
    def total(self) -> int:
        return sum(int(b["amount"]) for b in self.bets)

    def _check_bet(self, seat: int, action: Action) -> tuple[str, Any, tuple[int, ...], int]:
        if seat != 0:
            raise IllegalMove("no such seat")
        if self.finished:
            raise IllegalMove("already spun")
        if len(self.bets) >= MAX_BETS:
            raise IllegalMove("too many bets")
        kind = action.get("bet")
        if not isinstance(kind, str):
            raise IllegalMove("unknown bet")
        target = action.get("target")
        nums = numbers_of(kind, target)
        amount = action.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 1:
            raise IllegalMove("bad amount")
        if self.total + amount > self.max_total:
            raise IllegalMove("over the table limit")
        if kind in VALID_SETS:
            target = list(nums)
        return kind, target, nums, amount

    def to_act(self) -> list[int]:
        return [] if self.finished else [0]

    def legal(self, seat: int) -> list[Action]:
        if seat != 0 or self.finished:
            return []
        out: list[Action] = []
        room = self.max_total - self.total
        if room >= 1 and len(self.bets) < MAX_BETS:
            out = [{"type": "bet", "bet": k, "min": 1, "max": room} for k in PAYS]
        if self.bets:
            out.append({"type": "spin"})
        return out

    def cost(self, seat: int, action: Action) -> int:
        kind = action.get("type")
        if kind == "bet":
            return self._check_bet(seat, action)[3]
        if kind == "spin":
            return 0
        raise IllegalMove("unknown action")

    def act(self, seat: int, action: Action) -> None:
        kind = action.get("type")
        if kind == "bet":
            bet, target, nums, amount = self._check_bet(seat, action)
            self.bets.append(
                {"bet": bet, "target": target, "numbers": list(nums), "amount": amount}
            )
            self.log.add("bet", seat=0, bet=bet, target=target, amount=amount)
            return
        if kind != "spin" or seat != 0 or self.finished:
            raise IllegalMove("not now")
        if not self.bets:
            raise IllegalMove("place a bet first")
        self.result = WHEEL_ORDER[self.rng.randrange(len(WHEEL_ORDER))]
        self.log.add("spin", number=self.result, color=color(self.result), win=self.win)

    def _gross(self, bet: dict[str, Any]) -> int:
        if self.result is None or self.result not in bet["numbers"]:
            return 0
        return int(bet["amount"]) * (PAYS[bet["bet"]] + 1)

    @property
    def win(self) -> int:
        return sum(self._gross(b) for b in self.bets)

    @property
    def finished(self) -> bool:
        return self.result is not None

    def payouts(self) -> dict[int, int]:
        return {0: self.win} if self.finished else {}

    def summary(self) -> dict[str, Any]:
        return {"result": self.result, "total": self.total, "win": self.win}

    def bot_action(self, seat: int) -> Action:
        if not self.bets:
            amount = min(self.max_total, max(1, self.stake))
            return {"type": "bet", "bet": "red", "amount": amount}
        return {"type": "spin"}

    def view(self, seat: int | None) -> dict[str, Any]:
        done = self.result is not None
        return {
            "phase": "done" if done else "bet",
            "bets": [
                {**b, "pays": PAYS[b["bet"]], "win": self._gross(b) if done else None}
                for b in self.bets
            ],
            "total": self.total,
            "maxTotal": self.max_total,
            "result": self.result,
            "color": color(self.result) if self.result is not None else None,
            "win": self.win,
            "wheel": list(WHEEL_ORDER),
            "red": sorted(RED),
            "pays": dict(PAYS),
        }
