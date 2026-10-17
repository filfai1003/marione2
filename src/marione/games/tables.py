"""Tables: seats, money, bots and timing around a pure `Game`.

A table is created by a member for one game and mode. Empty seats can be left for friends or
given to Marione's bots; a solo table starts at once. Money goes through a `Wallet` (the ledger):

* ``stake`` games: each human pays the stake when a match starts; at the end the pot (stake x
  seats, bots' share paid by the house) is split among the winners, a draw refunds everyone.
* ``bets`` games: an action's `cost` is debited before the game sees it; `payouts` are credited.

Coins in play are recorded as escrow, so a restart refunds a match that never ended. Tables live
in memory: the page polls `state` with the version it has and waits for the next change.
"""

import asyncio
import contextlib
import logging
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from marione.games.base import Action, Game, IllegalMove, Mode
from marione.games.registry import GAMES

logger = logging.getLogger("marione.games")

MAX_TABLES = 40
MAX_TABLES_PER_USER = 3
TURN_SECONDS = 75.0  # a human who does not move in time is played for by a bot
IDLE_SECONDS = 20 * 60.0  # a table nobody touched for this long is closed
BOT_DELAY = (0.7, 1.4)
MAX_STAKE = 1_000_000

BOT_NAMES = ("Marione", "Nonna Pina", "Zio Peppe", "Cugino Gigi", "La Sciura", "Don Raffaele")


class Wallet(Protocol):
    async def debit(self, user_id: int, amount: int, key: str) -> int: ...
    async def credit(self, user_id: int, amount: int, reason: str, key: str) -> int: ...
    async def escrow(self, table_id: str, user_id: int, amount: int) -> None: ...
    async def release(self, table_id: str) -> None: ...
    async def result(self, game: str, user_id: int, net: int) -> None: ...


class TableError(Exception):
    def __init__(self, code: str, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.extra = extra


@dataclass
class Seat:
    user_id: int | None  # None: a bot
    name: str
    auto: bool = False  # a human who timed out is being played for

    @property
    def bot(self) -> bool:
        return self.user_id is None


@dataclass
class Table:
    id: str
    game_key: str
    mode: Mode
    stake: int
    owner_id: int
    seats: list[Seat | None]
    options: dict[str, Any] = field(default_factory=dict)
    status: str = "waiting"  # waiting | playing | over | closed
    game: Game | None = None
    round: int = 0
    version: int = 0
    touched: float = 0.0
    turn_since: float = 0.0
    last_result: dict[str, Any] | None = None
    paid: dict[int, int] = field(default_factory=dict)  # coins each human has in play this round
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def seat_of(self, user_id: int) -> int | None:
        for i, s in enumerate(self.seats):
            if s is not None and s.user_id == user_id:
                return i
        return None

    @property
    def humans(self) -> list[int]:
        return [s.user_id for s in self.seats if s is not None and s.user_id is not None]

    @property
    def full(self) -> bool:
        return all(s is not None for s in self.seats)


class GameHall:
    def __init__(
        self,
        wallet: Wallet,
        *,
        clock: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
        bot_delay: tuple[float, float] = BOT_DELAY,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._wallet = wallet
        self._clock = clock
        self._rng = rng or random.SystemRandom()
        self._bot_delay = bot_delay
        self._sleep = sleep
        self.tables: dict[str, Table] = {}
        self._runners: dict[str, asyncio.Task[None]] = {}

    # --- lobby -------------------------------------------------------------------------------

    def lobby(self) -> list[Table]:
        return [t for t in self.tables.values() if t.status != "closed"]

    def get(self, table_id: str) -> Table:
        table = self.tables.get(table_id)
        if table is None or table.status == "closed":
            raise TableError("not_found")
        return table

    async def create(
        self,
        user_id: int,
        name: str,
        game_key: str,
        mode_key: str,
        stake: int,
        *,
        bots: bool,
        options: dict[str, Any] | None = None,
    ) -> Table:
        cls = GAMES.get(game_key)
        if cls is None:
            raise TableError("unknown_game")
        mode = next((m for m in cls.modes if m.key == mode_key), None)
        if mode is None:
            raise TableError("unknown_mode")
        if not 0 <= stake <= MAX_STAKE:
            raise TableError("bad_stake")
        if len(self.lobby()) >= MAX_TABLES:
            raise TableError("too_many_tables")
        yours = [t for t in self.lobby() if user_id in t.humans]
        if len(yours) >= MAX_TABLES_PER_USER:
            # Tables you play alone against bots are cheap to leave: close the oldest one.
            alone = [t for t in yours if t.humans == [user_id]]
            if not alone:
                raise TableError("too_many_yours")
            oldest = min(alone, key=lambda t: t.touched)
            async with oldest.lock:
                await self._close(oldest)
                self._bump(oldest)
        table = Table(
            id=secrets.token_hex(5),
            game_key=game_key,
            mode=mode,
            stake=stake,
            owner_id=user_id,
            seats=[None] * mode.seats,
            options=dict(options or {}),
            touched=self._clock(),
        )
        table.seats[0] = Seat(user_id, name)
        self.tables[table.id] = table
        if bots or mode.seats == 1:
            self._fill_bots(table)
            await self.start(user_id, table.id)
        else:
            self._bump(table)
        return table

    def _fill_bots(self, table: Table) -> None:
        for i, s in enumerate(table.seats):
            if s is None:
                table.seats[i] = Seat(None, BOT_NAMES[i % len(BOT_NAMES)] + " 🤖")

    async def join(self, user_id: int, name: str, table_id: str, seat: int | None = None) -> Table:
        table = self.get(table_id)
        async with table.lock:
            if table.seat_of(user_id) is not None:
                return table
            if table.status != "waiting":
                raise TableError("already_started")
            free = [i for i, s in enumerate(table.seats) if s is None or s.bot]
            if seat is not None and seat not in free:
                raise TableError("seat_taken")
            if not free:
                raise TableError("table_full")
            table.seats[seat if seat is not None else free[0]] = Seat(user_id, name)
            self._bump(table)
        return table

    async def leave(self, user_id: int, table_id: str) -> None:
        table = self.get(table_id)
        async with table.lock:
            i = table.seat_of(user_id)
            if i is None:
                return
            if table.status == "playing":
                seat = table.seats[i]
                assert seat is not None
                seat.auto = True  # the match goes on; a bot plays for them (money stays in play)
            else:
                table.seats[i] = None
            if not table.humans or all(s is None or s.bot or s.auto for s in table.seats):
                await self._close(table)
            elif table.owner_id == user_id:
                table.owner_id = table.humans[0]
            self._bump(table)

    async def add_bot(self, user_id: int, table_id: str) -> None:
        table = self.get(table_id)
        async with table.lock:
            if user_id != table.owner_id or table.status != "waiting":
                raise TableError("forbidden")
            free = [i for i, s in enumerate(table.seats) if s is None]
            if not free:
                raise TableError("table_full")
            table.seats[free[0]] = Seat(None, BOT_NAMES[free[0] % len(BOT_NAMES)] + " 🤖")
            self._bump(table)

    async def kick_bot(self, user_id: int, table_id: str, seat: int) -> None:
        table = self.get(table_id)
        async with table.lock:
            if user_id != table.owner_id or table.status != "waiting":
                raise TableError("forbidden")
            s = table.seats[seat] if 0 <= seat < len(table.seats) else None
            if s is None or not s.bot:
                raise TableError("not_a_bot")
            table.seats[seat] = None
            self._bump(table)

    # --- a match -----------------------------------------------------------------------------

    async def start(self, user_id: int, table_id: str) -> Table:
        """Start (or restart, after a match) with whoever is seated; empty seats become bots."""
        table = self.get(table_id)
        async with table.lock:
            if table.seat_of(user_id) is None:
                raise TableError("forbidden")
            if table.status == "playing":
                return table
            if table.status == "waiting" and user_id != table.owner_id:
                raise TableError("forbidden")
            for s in table.seats:
                if s is not None:
                    s.auto = False
            if not table.full:
                self._fill_bots(table)
            cls = GAMES[table.game_key]
            if cls.economy == "stake" and table.stake > 0:
                await self._collect_stakes(table)
            table.round += 1
            options = {**table.options, "stake": table.stake}
            table.game = cls(table.mode, random.Random(self._rng.random()), options)
            table.status = "playing"
            table.turn_since = self._clock()
            table.last_result = None
            self._bump(table)
        self._run(table)
        return table

    async def _collect_stakes(self, table: Table) -> None:
        taken: dict[int, int] = {}
        for uid in table.humans:
            got = await self._wallet.debit(
                uid, table.stake, f"game:{table.id}:{table.round + 1}:{uid}:stake"
            )
            taken[uid] = got
            if got < table.stake:
                for back_uid, amount in taken.items():
                    if amount:
                        await self._wallet.credit(
                            back_uid,
                            amount,
                            "game_refund",
                            f"game:{table.id}:{table.round + 1}:{back_uid}:short",
                        )
                raise TableError("insufficient_funds", userId=str(uid))
        for uid, amount in taken.items():
            table.paid[uid] = amount
            await self._wallet.escrow(table.id, uid, amount)

    async def act(self, user_id: int, table_id: str, action: Action) -> Table:
        table = self.get(table_id)
        if table.status == "over" and GAMES[table.game_key].house:
            await self.start(
                user_id, table_id
            )  # against the bank, the next round starts by playing
        async with table.lock:
            seat = table.seat_of(user_id)
            if seat is None:
                raise TableError("forbidden")
            await self._apply(table, seat, action)
        self._run(table)
        return table

    async def _apply(self, table: Table, seat: int, action: Action) -> None:
        game = table.game
        if table.status != "playing" or game is None:
            raise TableError("not_playing")
        if seat not in game.to_act():
            raise TableError("not_your_turn")
        s = table.seats[seat]
        assert s is not None
        try:
            cost = game.cost(seat, action)
        except IllegalMove as exc:
            raise TableError("illegal", detail=str(exc)) from exc
        if cost < 0:
            raise TableError("illegal")
        if cost and s.user_id is not None:
            key = f"game:{table.id}:{table.round}:{s.user_id}:{secrets.token_hex(6)}"
            got = await self._wallet.debit(s.user_id, cost, key)
            if got < cost:
                if got:
                    await self._wallet.credit(s.user_id, got, "game_refund", key + ":back")
                raise TableError("insufficient_funds")
            table.paid[s.user_id] = table.paid.get(s.user_id, 0) + cost
            await self._wallet.escrow(table.id, s.user_id, cost)
        try:
            game.act(seat, action)
        except IllegalMove as exc:
            if cost and s.user_id is not None:
                table.paid[s.user_id] -= cost
                await self._wallet.credit(
                    s.user_id, cost, "game_refund", f"game:{table.id}:{secrets.token_hex(6)}"
                )
            raise TableError("illegal", detail=str(exc)) from exc
        table.turn_since = self._clock()
        if game.finished:
            await self._settle(table)
        self._bump(table)

    async def _settle(self, table: Table) -> None:
        game = table.game
        assert game is not None
        cls = type(game)
        gross: dict[int, int] = {}
        if cls.economy == "stake":
            pot = table.stake * len(table.seats)
            weights = game.split()
            if not weights:
                weights = dict.fromkeys(game.winners(), 1)
            total = sum(weights.values())
            if total <= 0:  # a draw: everyone gets the stake back
                gross = dict.fromkeys(range(len(table.seats)), table.stake)
            else:
                gross = {w: pot * n // total for w, n in weights.items() if n > 0}
                first = next(iter(gross))
                gross[first] += pot - sum(gross.values())
        else:
            gross = game.payouts()
        nets: dict[int, int] = {}
        for i, s in enumerate(table.seats):
            if s is None or s.user_id is None:
                continue
            amount = gross.get(i, 0)
            if amount > 0:
                await self._wallet.credit(
                    s.user_id, amount, "game_win", f"game:{table.id}:{table.round}:{s.user_id}:win"
                )
            nets[s.user_id] = amount - table.paid.get(s.user_id, 0)
            await self._wallet.result(table.game_key, s.user_id, nets[s.user_id])
        await self._wallet.release(table.id)
        table.paid = {}
        table.status = "over"
        table.last_result = {
            **game.summary(),
            "nets": {str(uid): net for uid, net in nets.items()},
            "gross": {str(k): v for k, v in gross.items()},
        }

    async def _close(self, table: Table) -> None:
        """Close a table; coins still in play go back to their owners."""
        for uid, amount in table.paid.items():
            if amount > 0:
                await self._wallet.credit(
                    uid, amount, "game_refund", f"game:{table.id}:{table.round}:{uid}:close"
                )
        table.paid = {}
        await self._wallet.release(table.id)
        table.status = "closed"
        runner = self._runners.pop(table.id, None)
        if runner is not None and runner is not asyncio.current_task():
            runner.cancel()

    # --- bots, timeouts and housekeeping -----------------------------------------------------

    def _run(self, table: Table) -> None:
        """Make sure a task is moving the bots of this table."""
        task = self._runners.get(table.id)
        if task is None or task.done():
            self._runners[table.id] = asyncio.create_task(self._drive(table))

    async def _drive(self, table: Table) -> None:
        while table.status == "playing" and table.game is not None:
            game = table.game
            waiting = game.to_act()
            movers = [i for i in waiting if (s := table.seats[i]) is not None and (s.bot or s.auto)]
            if not movers:
                return
            await self._sleep(self._rng.uniform(*self._bot_delay))
            async with table.lock:
                if table.status != "playing" or table.game is not game:
                    return
                seat = next((i for i in game.to_act() if i in movers), None)
                if seat is None:
                    continue
                try:
                    move = await asyncio.to_thread(game.bot_action, seat)  # chess thinks a while
                    await self._apply(table, seat, move)
                except TableError as exc:
                    logger.error("bot move refused in %s: %s", table.game_key, exc.code)
                    await self._close(table)
                    self._bump(table)
                    return

    async def tick(self) -> None:
        """Called every few seconds: time out slow humans, close abandoned tables."""
        now = self._clock()
        for table in list(self.tables.values()):
            if table.status == "closed":
                if now - table.touched > 60:
                    self.tables.pop(table.id, None)
                continue
            if now - table.touched > IDLE_SECONDS:
                async with table.lock:
                    await self._close(table)
                    self._bump(table)
                continue
            game = table.game
            playing = table.status == "playing" and game is not None and len(table.humans) > 1
            if playing and game is not None and now - table.turn_since > TURN_SECONDS:
                async with table.lock:
                    for i in game.to_act():
                        s = table.seats[i]
                        if s is not None and not s.bot:
                            s.auto = True
                    self._bump(table)
                self._run(table)

    async def shutdown(self) -> None:
        for table in list(self.tables.values()):
            if table.status != "closed":
                async with table.lock:
                    await self._close(table)

    def _bump(self, table: Table) -> None:
        table.version += 1
        table.touched = self._clock()
        event, table.changed = table.changed, asyncio.Event()
        event.set()

    async def wait(self, table_id: str, version: int, seconds: float = 25.0) -> Table:
        """Return as soon as the table is newer than `version` (or after `seconds`)."""
        table = self.get(table_id)
        if table.version > version:
            return table
        event = table.changed
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), seconds)
        return table

    # --- what the page gets ------------------------------------------------------------------

    def view(self, table: Table, user_id: int | None) -> dict[str, Any]:
        seat = table.seat_of(user_id) if user_id is not None else None
        game = table.game
        to_act = game.to_act() if game is not None and table.status == "playing" else []
        return {
            "id": table.id,
            "game": table.game_key,
            "mode": table.mode.key,
            "teams": [list(t) for t in table.mode.teams],
            "stake": table.stake,
            "status": table.status,
            "round": table.round,
            "version": table.version,
            "owner": str(table.owner_id),
            "you": seat,
            "seats": [
                None
                if s is None
                else {
                    "name": s.name,
                    "bot": s.bot,
                    "auto": s.auto,
                    "userId": str(s.user_id) if s.user_id else None,
                }
                for s in table.seats
            ],
            "toAct": to_act,
            "legal": game.legal(seat)
            if game is not None and seat is not None and seat in to_act
            else [],
            "state": game.view(seat) if game is not None else None,
            "log": game.log.entries[-12:] if game is not None else [],
            "result": table.last_result,
            "turnLeft": max(0, int(TURN_SECONDS - (self._clock() - table.turn_since)))
            if to_act and len(table.humans) > 1
            else None,
        }

    def summary(self, table: Table) -> dict[str, Any]:
        return {
            "id": table.id,
            "game": table.game_key,
            "mode": table.mode.key,
            "stake": table.stake,
            "status": table.status,
            "seats": [None if s is None else {"name": s.name, "bot": s.bot} for s in table.seats],
            "free": sum(1 for s in table.seats if s is None),
            "humans": [str(u) for u in table.humans],
        }
