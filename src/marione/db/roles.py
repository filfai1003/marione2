"""The Discord roles Marione created for the wealth tiers (so it never touches anyone else's)."""

from marione.db.pool import Pool


class RolesRepo:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def all(self) -> dict[str, int]:
        rows = await self._pool.fetch("select tier_key, role_id from marione.wealth_roles")
        return {r["tier_key"]: r["role_id"] for r in rows}

    async def set(self, tier_key: str, role_id: int) -> None:
        await self._pool.execute(
            "insert into marione.wealth_roles (tier_key, role_id) values ($1, $2)"
            " on conflict (tier_key) do update set role_id = excluded.role_id",
            tier_key,
            role_id,
        )

    async def clear(self) -> None:
        await self._pool.execute("delete from marione.wealth_roles")
