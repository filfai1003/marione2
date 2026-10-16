"""Robbery attempts: the cooldown and the money movement live in one SQL function."""

import secrets
from dataclasses import dataclass

from marione.db.pool import Pool


@dataclass(frozen=True)
class HeistResult:
    status: str  # "ok" | "caught" | "cooldown" | "victim_poor"
    moved: int
    wait_seconds: int


class HeistRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def resolve(
        self,
        attacker: int,
        victim: int,
        amount: int,
        *,
        success: bool,
        fine: int,
        cooldown_seconds: int,
    ) -> HeistResult:
        row = await self._pool.fetchrow(
            "select * from marione.resolve_heist($1, $2, $3, $4, $5, $6, $7)",
            attacker,
            victim,
            amount,
            success,
            fine,
            cooldown_seconds,
            f"heist:{secrets.token_hex(8)}",
        )
        assert row is not None
        return HeistResult(row["status"], int(row["moved"]), int(row["wait_seconds"]))

    async def cooldown_remaining(self, attacker: int, cooldown_seconds: int) -> int:
        value = await self._pool.fetchval(
            "select greatest(0, ceil($2 - extract(epoch from (now() - max(created_at)))))::int"
            " from marione.heists where attacker_id = $1",
            attacker,
            cooldown_seconds,
        )
        return int(value or 0)
