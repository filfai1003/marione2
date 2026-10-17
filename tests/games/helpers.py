"""Shared test helpers for games: play a whole match with bots, a wallet in memory."""

import random
from typing import Any

from marione.games.base import Game, Mode


def play_out(
    cls: type[Game], mode: Mode, seed: int, options: dict[str, Any] | None = None, limit: int = 5000
) -> Game:
    """Every seat played by the bot until the end; checks each bot move is in `legal`."""
    game = cls(mode, random.Random(seed), options)
    for _ in range(limit):
        if game.finished:
            return game
        seat = game.to_act()[0]
        action = game.bot_action(seat)
        legal = game.legal(seat)
        assert any(_matches(action, a) for a in legal), (action, legal)
        game.act(seat, action)
        for s in range(game.seats):
            game.view(s)
    raise AssertionError("the match never ended")


def _matches(action: dict[str, Any], legal: dict[str, Any]) -> bool:
    """An action fits a legal entry: same keys and values, or within its min/max range."""
    for k, v in legal.items():
        if k in ("min", "max"):
            continue
        if action.get(k) != v:
            return False
    amount = action.get("amount")
    if "min" in legal and amount is not None:
        return bool(legal["min"] <= amount <= legal.get("max", amount))
    return True


class MemoryWallet:
    def __init__(self, balances: dict[int, int]) -> None:
        self.balances = dict(balances)
        self.escrowed: dict[str, dict[int, int]] = {}
        self.results: list[tuple[str, int, int]] = []
        self.keys: set[str] = set()

    async def debit(self, user_id: int, amount: int, key: str) -> int:
        assert key not in self.keys
        self.keys.add(key)
        taken = min(amount, self.balances.get(user_id, 0))
        self.balances[user_id] = self.balances.get(user_id, 0) - taken
        return taken

    async def credit(self, user_id: int, amount: int, reason: str, key: str) -> int:
        assert key not in self.keys
        self.keys.add(key)
        self.balances[user_id] = self.balances.get(user_id, 0) + amount
        return amount

    async def escrow(self, table_id: str, user_id: int, amount: int) -> None:
        pile = self.escrowed.setdefault(table_id, {})
        pile[user_id] = pile.get(user_id, 0) + amount

    async def release(self, table_id: str) -> None:
        self.escrowed.pop(table_id, None)

    async def result(self, game: str, user_id: int, net: int) -> None:
        self.results.append((game, user_id, net))
