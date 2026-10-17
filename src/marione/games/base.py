"""The contract every game follows. A game is a pure state machine: no I/O, no clock, and all its
randomness comes from the `random.Random` it is given, so tests can replay any deal.

A table (see `tables.py`) owns the seats, the money and the timing; the game only knows seats
0..n-1, whose turn it is, what is legal, what each seat may see, and who won.

Two ways money moves, chosen by `Game.economy`:

* ``"stake"``: everyone pays the table's stake when a match starts; at the end the pot is split
  among `winners()` (a draw, or no winners, gives everyone their stake back). Card games, chess.
* ``"bets"``: the game asks for coins as it goes (`cost` of an action: a bet, a raise, a double)
  and pays out at the end (`payouts`, gross). Casino games and poker. Against the house, payouts
  may exceed what was bet; between players they sum to what was bet.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

Action = dict[str, Any]
Economy = Literal["stake", "bets"]


class IllegalMove(Exception):
    """The action is not allowed now (wrong turn, wrong card, not enough chips...)."""


@dataclass(frozen=True)
class Mode:
    """One way to play a game: how many seats and, for team games, who plays with whom."""

    key: str  # "1v1", "2v2", "1v1v1", "solo", "table"
    seats: int
    teams: tuple[tuple[int, ...], ...] = ()  # empty = every seat for itself
    min_humans: int = 1

    def team_of(self, seat: int) -> int:
        for i, team in enumerate(self.teams):
            if seat in team:
                return i
        return seat


@dataclass
class Log:
    """Short human-readable events the page shows ("Anna plays 7♦", "Bank busts")."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def add(self, kind: str, **data: Any) -> None:
        self.entries.append({"kind": kind, **data})
        del self.entries[:-40]


class Game(ABC):
    key: ClassVar[str]
    modes: ClassVar[tuple[Mode, ...]]
    economy: ClassVar[Economy] = "stake"
    house: ClassVar[bool] = False  # True: played against the bank (slot, roulette, blackjack)

    def __init__(self, mode: Mode, rng: random.Random, options: dict[str, Any] | None = None):
        self.mode = mode
        self.rng = rng
        self.options = options or {}
        self.stake = int(
            self.options.get("stake", 0)
        )  # the table's stake: the base bet in bets games
        self.log = Log()

    @property
    def seats(self) -> int:
        return self.mode.seats

    # --- turn and moves ----------------------------------------------------------------------

    @abstractmethod
    def to_act(self) -> list[int]:
        """Seats whose action is awaited now (usually one; empty once finished)."""

    @abstractmethod
    def legal(self, seat: int) -> list[Action]:
        """Every action `seat` may take now. Actions with a free amount (a bet) appear once,
        with "min"/"max" keys; `act` validates the actual amount."""

    @abstractmethod
    def act(self, seat: int, action: Action) -> None:
        """Apply an action; raise IllegalMove if it is not allowed."""

    def cost(self, seat: int, action: Action) -> int:
        """Coins this action needs from the seat's balance (``bets`` games). 0 by default."""
        return 0

    @abstractmethod
    def bot_action(self, seat: int) -> Action:
        """What a computer player does in `seat` now (must be legal)."""

    # --- what people see ---------------------------------------------------------------------

    @abstractmethod
    def view(self, seat: int | None) -> dict[str, Any]:
        """The state as `seat` may see it (None = a spectator). Never leak hidden cards."""

    # --- the end -----------------------------------------------------------------------------

    @property
    @abstractmethod
    def finished(self) -> bool: ...

    def winners(self) -> list[int]:
        """``stake`` games: the seats that split the pot (all seats of the winning team)."""
        return []

    def split(self) -> dict[int, int]:
        """``stake`` games that share the pot unevenly: weight per seat (e.g. tricks taken).
        Empty = split evenly among `winners()`."""
        return {}

    def payouts(self) -> dict[int, int]:
        """``bets`` games: gross coins each seat receives at the end."""
        return {}

    def summary(self) -> dict[str, Any]:
        """Final result for the page: scores, hands, the reason the match ended."""
        return {}


def team_winners(mode: Mode, winning_team: int | None) -> list[int]:
    """All the seats of a team (or, without teams, the single seat)."""
    if winning_team is None:
        return []
    if mode.teams:
        return list(mode.teams[winning_team])
    return [winning_team]
