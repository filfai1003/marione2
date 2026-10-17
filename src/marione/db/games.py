"""Money for the games table manager (the `Wallet` it expects) and the results of matches."""

from typing import Any

from marione.db.ledger import Ledger
from marione.db.pool import Pool


class GamesRepo:
    def __init__(self, pool: Pool, ledger: Ledger) -> None:
        self._pool = pool
        self._ledger = ledger

    # --- Wallet ------------------------------------------------------------------------------

    async def debit(self, user_id: int, amount: int, key: str) -> int:
        return await self._ledger.debit(user_id, amount, "game_bet", key=key)

    async def credit(self, user_id: int, amount: int, reason: str, key: str) -> int:
        return await self._ledger.credit(user_id, amount, reason, key=key)

    async def escrow(self, table_id: str, user_id: int, amount: int) -> None:
        if amount > 0:
            await self._pool.execute(
                "insert into marione.game_escrow (table_id, user_id, amount) values ($1, $2, $3)",
                table_id,
                user_id,
                amount,
            )

    async def release(self, table_id: str) -> None:
        await self._pool.execute("delete from marione.game_escrow where table_id = $1", table_id)

    async def result(self, game: str, user_id: int, net: int) -> None:
        await self._pool.execute(
            "insert into marione.game_results (game, user_id, net) values ($1, $2, $3)",
            game,
            user_id,
            net,
        )

    # --- after a restart ---------------------------------------------------------------------

    async def refund_leftovers(self) -> int:
        """Give back coins still in escrow (matches cut short by a restart). Returns the count."""
        rows = await self._pool.fetch(
            "select table_id, user_id, sum(amount) as amount from marione.game_escrow"
            " group by table_id, user_id"
        )
        for row in rows:
            await self._ledger.credit(
                row["user_id"],
                int(row["amount"]),
                "game_refund",
                key=f"game-restart:{row['table_id']}:{row['user_id']}",
            )
            await self._pool.execute(
                "delete from marione.game_escrow where table_id = $1 and user_id = $2",
                row["table_id"],
                row["user_id"],
            )
        return len(rows)

    # --- stats -------------------------------------------------------------------------------

    async def stats(self, user_id: int) -> list[dict[str, Any]]:
        rows = await self._pool.fetch(
            "select game, count(*) as played, count(*) filter (where net > 0) as won,"
            " coalesce(sum(net), 0) as net from marione.game_results where user_id = $1"
            " group by game",
            user_id,
        )
        return [
            {"game": r["game"], "played": r["played"], "won": r["won"], "net": int(r["net"])}
            for r in rows
        ]

    async def top_winners(self, days: int = 7, limit: int = 5) -> list[tuple[int, str, int]]:
        rows = await self._pool.fetch(
            "select r.user_id, coalesce(m.display_name, '') as name, sum(r.net) as net"
            " from marione.game_results r left join marione.members m using (user_id)"
            " where r.created_at > now() - make_interval(days => $1)"
            " group by r.user_id, m.display_name having sum(r.net) > 0"
            " order by net desc limit $2",
            days,
            limit,
        )
        return [(r["user_id"], r["name"], int(r["net"])) for r in rows]
