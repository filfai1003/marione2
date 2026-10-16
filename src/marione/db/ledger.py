"""The economy: balances backed by an append-only ledger.

Every change is one entry. A balance is the sum of its entries, kept in step inside the same
transaction by the SQL functions in `migrations/0001_core.sql`. Nothing here keeps state in
memory, so a crash can never lose or duplicate coins.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from marione.db.pool import Pool


@dataclass(frozen=True)
class LedgerEntry:
    id: int
    group_id: UUID
    user_id: int
    delta: int
    reason: str
    counterparty: int | None
    created_at: datetime
    meta: dict[str, Any]


def _entry(row: Any) -> LedgerEntry:
    meta = row["meta"]
    return LedgerEntry(
        id=row["id"],
        group_id=row["group_id"],
        user_id=row["user_id"],
        delta=row["delta"],
        reason=row["reason"],
        counterparty=row["counterparty"],
        created_at=row["created_at"],
        meta=json.loads(meta) if isinstance(meta, str) else dict(meta),
    )


class Ledger:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def remember_name(self, user_id: int, name: str) -> None:
        """Keep the last known display name, so members who left still show in the ranking."""
        await self._pool.execute(
            "insert into marione.members (user_id, display_name) values ($1, $2)"
            " on conflict (user_id) do update set display_name = excluded.display_name,"
            " updated_at = now() where marione.members.display_name <> excluded.display_name",
            user_id,
            name,
        )

    async def name_of(self, user_id: int, default: str = "") -> str:
        row = await self._pool.fetchrow(
            "select display_name from marione.members where user_id = $1", user_id
        )
        return row["display_name"] or default if row else default

    async def balance(self, user_id: int) -> int:
        value = await self._pool.fetchval(
            "select balance from marione.balances where user_id = $1", user_id
        )
        return int(value or 0)

    async def credit(
        self, user_id: int, amount: int, reason: str, *, key: str | None = None
    ) -> int:
        """Add coins. Returns the amount applied (0 if this key was already used)."""
        if amount <= 0:
            raise ValueError("credit needs a positive amount")
        return int(
            await self._pool.fetchval(
                "select marione.apply_delta($1, $2, $3, null, $4)", user_id, amount, reason, key
            )
        )

    async def debit(self, user_id: int, amount: int, reason: str, *, key: str | None = None) -> int:
        """Take up to `amount` coins (never below zero). Returns the amount really taken."""
        if amount <= 0:
            raise ValueError("debit needs a positive amount")
        applied = await self._pool.fetchval(
            "select marione.apply_delta($1, $2, $3, null, $4)", user_id, -amount, reason, key
        )
        return -int(applied)

    async def set_balance(self, user_id: int, target: int, *, admin_id: int) -> int:
        """Admin: set a balance by writing the difference as one auditable entry."""
        if target < 0:
            raise ValueError("a balance cannot be negative")
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "insert into marione.members (user_id) values ($1) on conflict do nothing", user_id
            )
            await conn.execute(
                "insert into marione.balances (user_id) values ($1) on conflict do nothing", user_id
            )
            current = int(
                await conn.fetchval(
                    "select balance from marione.balances where user_id = $1 for update", user_id
                )
            )
            delta = target - current
            if delta:
                await conn.fetchval(
                    "select marione.apply_delta($1, $2, 'admin_adjust', $3, null, $4, false)",
                    user_id,
                    delta,
                    admin_id,
                    json.dumps({"kind": "set", "from": current, "to": target}),
                )
            return delta

    async def pay(self, sender: int, receiver: int, amount: int, *, key: str | None = None) -> bool:
        """A payment between members: all of it or nothing."""
        moved = await self._pool.fetchval(
            "select marione.move($1, $2, $3, 'transfer_out', 'transfer_in', $4)",
            sender,
            receiver,
            amount,
            key,
        )
        return int(moved) == amount

    async def agent_gift(
        self, bot_id: int, target: int, amount: int, meta: dict[str, Any]
    ) -> tuple[int, UUID | None]:
        """A gift paid by the bot's own account. Returns (moved, operation id)."""
        return await self._move_group(
            bot_id, target, amount, "agent_gift_out", "agent_gift_in", meta, partial=False
        )

    async def agent_fine(
        self, bot_id: int, target: int, amount: int, meta: dict[str, Any]
    ) -> tuple[int, UUID | None]:
        """A fine: takes up to `amount` from the member; the coins go to the bot."""
        return await self._move_group(
            target, bot_id, amount, "agent_fine_out", "agent_fine_in", meta, partial=True
        )

    async def _move_group(
        self,
        sender: int,
        receiver: int,
        amount: int,
        reason_out: str,
        reason_in: str,
        meta: dict[str, Any],
        *,
        partial: bool,
    ) -> tuple[int, UUID | None]:
        group = uuid4()
        moved = int(
            await self._pool.fetchval(
                "select marione.move($1, $2, $3, $4, $5, null, $6, $7, $8)",
                sender,
                receiver,
                amount,
                reason_out,
                reason_in,
                json.dumps(meta),
                partial,
                group,
            )
        )
        return (moved, group) if moved else (0, None)

    async def reverse(self, group_id: UUID) -> int:
        """Undo a whole operation with compensating entries. Safe to repeat."""
        return int(await self._pool.fetchval("select marione.reverse_group($1)", group_id))

    async def group_of(self, entry_id: int) -> UUID | None:
        """The operation a ledger entry belongs to (what an admin undoes by entry number)."""
        value: UUID | None = await self._pool.fetchval(
            "select group_id from marione.ledger where id = $1", entry_id
        )
        return value

    async def last_agent_action(self, user_id: int) -> datetime | None:
        value: datetime | None = await self._pool.fetchval(
            "select max(created_at) from marione.ledger"
            " where user_id = $1 and reason in ('agent_fine_out', 'agent_gift_in')",
            user_id,
        )
        return value

    async def top(self, limit: int = 10) -> list[tuple[int, str, int]]:
        rows = await self._pool.fetch(
            "select b.user_id, m.display_name, b.balance from marione.balances b"
            " join marione.members m using (user_id) where b.balance > 0"
            " order by b.balance desc, b.user_id limit $1",
            limit,
        )
        return [(r["user_id"], r["display_name"], r["balance"]) for r in rows]

    async def history(self, user_id: int, limit: int = 20) -> list[LedgerEntry]:
        rows = await self._pool.fetch(
            "select * from marione.ledger where user_id = $1 order by id desc limit $2",
            user_id,
            limit,
        )
        return [_entry(r) for r in rows]

    async def audit(self) -> list[int]:
        """Members whose balance differs from their ledger. Must always be empty."""
        rows = await self._pool.fetch("select user_id from marione.balance_audit")
        return [r["user_id"] for r in rows]
